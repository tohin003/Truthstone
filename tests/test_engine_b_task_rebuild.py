"""R14 (engine): task state survives restarts and busy repositories.

`TaskState` lived in memory only, in a window of eight tasks kept in insertion order. D3
reproduced "Stop after failing tests -> allow" three ways (`x_state.py`): after a daemon
restart mid-task, with nine concurrent sessions, and with another session sending eight
prompts while the task was open. The window is now LRU by activity, capped at 64, and
never evicts a session's current task; a task the store knows is rebuilt from it.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from truthstone.adapters.claude_code import translate as claude
from truthstone.core import engine, rehydrate
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction
from truthstone.core.store import ProjectStore
from truthstone.daemon import degraded

FIXTURES = Path(__file__).parent / "fixtures"
USERS = "src/shop/api/users.py"
PAGINATION = "src/shop/utils/pagination.py"  # covered by tests/test_pagination.py
FAILING = {
    "stdout": (
        "F...\n=== FAILURES ===\nFAILED tests/test_user_repository.py::test_x\n"
        "1 failed, 3 passed in 0.2s\n"
    ),
    "stderr": "",
    "interrupted": False,
}
PASSING = {"stdout": "....\n4 passed in 0.2s\n", "stderr": "", "interrupted": False}


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


@pytest.fixture(autouse=True)
def _clean_registry():
    degraded.clear(engine.TASK_REBUILT)
    yield
    degraded.clear(engine.TASK_REBUILT)


def send(guard: Guard, repo: Path, name: str, session: str = "A", **fields):
    payload = {"session_id": session, "cwd": str(repo), "hook_event_name": name, **fields}
    return guard.handle(claude.to_event(payload))


def started(repo: Path) -> Guard:
    guard = Guard(Settings(profile="full"))
    assert guard.workspace(repo).index.ready(timeout=30)
    return guard


def edit(guard: Guard, repo: Path, session: str = "A", path: str = USERS) -> None:
    target = repo / path
    arguments = {"file_path": str(target), "old_string": "a", "new_string": "b"}
    send(guard, repo, "PreToolUse", session, tool_name="Edit", tool_input=arguments)
    target.write_text(target.read_text() + f"\n# {session} {time.time()}\n")
    send(guard, repo, "PostToolUse", session, tool_name="Edit", tool_input=arguments,
         tool_response={"filePath": str(target)})


def pytest_run(guard: Guard, repo: Path, response: dict, session: str = "A") -> None:
    command = {"command": "pytest -q"}
    send(guard, repo, "PreToolUse", session, tool_name="Bash", tool_input=command)
    send(guard, repo, "PostToolUse", session, tool_name="Bash", tool_input=command, tool_response=response)


def turn_with_failed_tests(guard: Guard, repo: Path, session: str = "A") -> None:
    send(guard, repo, "UserPromptSubmit", session, prompt="Add pagination to the users endpoint")
    edit(guard, repo, session)
    pytest_run(guard, repo, FAILING, session)


def stop(guard: Guard, repo: Path, session: str = "A"):
    return send(guard, repo, "Stop", session, last_assistant_message="Done. All tests pass.",
                stop_hook_active=False)


def test_failing_run_survives_daemon_restart(repo):
    first = started(repo)
    turn_with_failed_tests(first, repo)
    first.close()  # the daemon restarts: nothing in memory survives, the store does

    second = started(repo)
    try:
        held = stop(second, repo)
        assert held.action is DecisionAction.BLOCK
        assert "reported failures" in held.reason
        state = second.workspace(repo).task_state(None, "A")
        assert USERS in state.touched_files
        reason = {r.code: r for r in degraded.reasons()}[engine.TASK_REBUILT]
        assert (reason.detail["changes"], reason.detail["runs"]) == (1, 1)
        assert reason.message == engine.TASK_REBUILT_REASON, "no counts in the message (R9)"
    finally:
        second.close()


def test_the_rebuilt_timeline_goes_on(repo):
    """A pass before the restart and an edit after it: the pass is stale."""
    first = started(repo)
    send(first, repo, "UserPromptSubmit", prompt="Make paginate treat page 0 as page 1")
    edit(first, repo, path=PAGINATION)
    pytest_run(first, repo, PASSING)
    first.close()

    second = started(repo)
    try:
        edit(second, repo, path=PAGINATION)
        held = stop(second, repo)
        assert held.action is DecisionAction.BLOCK
        assert "changed after the last passing test run" in held.reason
        pytest_run(second, repo, PASSING)
        assert stop(second, repo).action is DecisionAction.ALLOW
    finally:
        second.close()


def test_nine_concurrent_sessions_keep_their_tasks(repo):
    guard = started(repo)
    try:
        turn_with_failed_tests(guard, repo, "A")
        for k in range(8):
            send(guard, repo, "UserPromptSubmit", f"other-{k}", prompt=f"Small change number {k} in models")
        assert guard.workspace(repo).task_state(None, "A") is not None
        assert stop(guard, repo, "A").action is DecisionAction.BLOCK
    finally:
        guard.close()


def test_eight_prompts_in_another_session_do_not_evict_mine(repo, monkeypatch):
    monkeypatch.setattr(engine, "MAX_LIVE_TASKS", 4)  # make the window bite
    guard = started(repo)
    try:
        ws = guard.workspace(repo)
        turn_with_failed_tests(guard, repo, "A")
        mine = ws.resolve_task_id("A")
        b_tasks = []
        for k in range(8):
            send(guard, repo, "UserPromptSubmit", "B", prompt=f"Quick question {k} about models")
            b_tasks.append(ws.resolve_task_id("B"))
        assert ws.live_task(mine) is not None, "a session's current task is never evicted"
        assert ws.live_task(b_tasks[0]) is None, "B's finished tasks went first"
        assert ws.live_task(b_tasks[-1]) is not None
        assert stop(guard, repo, "A").action is DecisionAction.BLOCK
        assert not {r.code for r in degraded.reasons()} & {engine.TASK_REBUILT}, "kept, not rebuilt"
    finally:
        guard.close()


def test_a_current_task_past_the_hard_cap_is_rebuilt(repo, monkeypatch):
    monkeypatch.setattr(engine, "MAX_LIVE_TASKS", 2)
    monkeypatch.setattr(engine, "HARD_MAX_LIVE_TASKS", 2)
    guard = started(repo)
    try:
        ws = guard.workspace(repo)
        turn_with_failed_tests(guard, repo, "A")
        mine = ws.resolve_task_id("A")
        for k in range(3):
            send(guard, repo, "UserPromptSubmit", f"s{k}", prompt=f"Change {k} in models")
        assert ws.live_task(mine) is None, "set aside past the hard cap"
        assert ws.resolve_task_id("A") == mine, "its session still points at it"
        assert stop(guard, repo, "A").action is DecisionAction.BLOCK
        assert engine.TASK_REBUILT in {r.code for r in degraded.reasons()}
    finally:
        guard.close()


def test_another_sessions_task_is_never_rebuilt_for_me(repo):
    first = started(repo)
    turn_with_failed_tests(first, repo, "A")
    task_id = first.workspace(repo).resolve_task_id("A")
    first.close()

    second = started(repo)
    try:
        ws = second.workspace(repo)
        assert ws.task_state(task_id, "B") is None
        assert ws.task_state(task_id, "A") is not None
    finally:
        second.close()


def test_a_closed_task_is_not_rebuilt(repo):
    first = started(repo)
    turn_with_failed_tests(first, repo, "A")
    task_id = first.workspace(repo).resolve_task_id("A")
    send(first, repo, "SessionEnd", "A")
    first.close()

    second = started(repo)
    try:
        assert second.workspace(repo).task_state(task_id, "A") is None
    finally:
        second.close()


def test_verification_rows_old_and_new():
    """Old rows hold command, summary and failed; the row's status decides; the suite is
    derived from the command when it is missing."""
    old = rehydrate.outcome_from_row(
        {"kind": "pytest", "status": "failed",
         "detail": {"command": "pytest tests/test_a.py -q", "summary": "1 failed", "failed": 1}}
    )
    assert (old.passed, old.runner, old.family, old.failed) == (False, "pytest", "python", 1)
    assert old.scope == ("tests/test_a.py",) and old.key
    new = rehydrate.outcome_from_row(
        {"kind": "pytest", "status": "passed",
         "detail": {"command": "npx jest", "summary": "ok", "failed": 0, "runner": "jest", "passed": False,
                    "total": 7, "exit_code": 0, "family": "js", "key": "jest", "scope": [],
                    "failing_files": []}}
    )
    assert (new.passed, new.runner, new.family, new.key, new.total, new.exit_code) == (
        True, "jest", "js", "jest", 7, 0
    ), "the status is authoritative for passed"
    unknown = rehydrate.outcome_from_row({"kind": "pytest", "status": "running", "detail": {}})
    assert unknown.passed is None and unknown.runner == "pytest"


def test_an_incomplete_spec_is_derived_again(repo):
    guard = started(repo)
    try:
        ws = guard.workspace(repo)
        store = ProjectStore.for_workspace(repo)
        prompt = "Fix paginate in src/shop/utils/pagination.py so page 0 is page 1"
        task_id = store.create_task("C", prompt, spec={"targets": ["t" * 100 for _ in range(100)]})
        assert store.task_record(task_id)["spec_complete"] is False
        state = ws.task_state(task_id, "C")
        assert state is not None and state.spec.prompt == prompt
        assert "src/shop/utils/pagination.py" in state.spec.expected_scope
    finally:
        guard.close()
