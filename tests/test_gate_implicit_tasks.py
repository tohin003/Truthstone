"""H2: implicit tasks.

A task used to exist only when a prompt event created one in the store. A host without a
prompt event, or a store that could not record the task, left none — so every challenge
became "no task context", and scope, test recording and the Completion Gate all
switched off (D5's probe; lead R1). Now the first tool event opens an implicit task, and
a prompt whose task cannot be stored keeps an in-memory one.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import DecisionAction, EventType
from agentguard.core.events import AgentEvent

FIXTURES = Path(__file__).parent / "fixtures"
COVERED = "src/shop/utils/pagination.py"


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


def _event(repo: Path, kind: EventType, tool: str | None = None, **args) -> AgentEvent:
    return AgentEvent(
        event=kind, agent="other-host", workspace=str(repo), session_id="s1", tool=tool, arguments=args
    )


def _edit(guard, repo: Path, path: str) -> list:
    full = repo / path
    full.parent.mkdir(parents=True, exist_ok=True)
    content = (full.read_text() if full.exists() else "") + "\n# changed\n"
    decisions = [guard.handle(_event(repo, EventType.PRE_TOOL_USE, "Write", file_path=path, content=content))]
    full.write_text(content)
    decisions.append(guard.handle(_event(repo, EventType.POST_TOOL_USE, "Write", file_path=path)))
    return decisions


def test_a_prompt_less_session_is_gated(guard, repo):
    """No prompt event at all: an edit to covered code, no tests, then Stop."""
    _edit(guard, repo, COVERED)
    state = guard.workspace(repo).task_state(None, "s1")
    assert state is not None and state.touched_files == {COVERED}
    decision = guard.handle(_event(repo, EventType.STOP))
    assert decision.action is DecisionAction.BLOCK
    assert "no tests were run" in decision.reason


def test_an_implicit_task_never_raises_proportionality(guard, repo):
    """Planning depth is not DIRECT for a task nobody described, so the DIRECT-band
    "this many files for a direct task" check cannot fire."""
    findings = []
    for i in range(10):
        for decision in _edit(guard, repo, f"src/shop/extra_{i}.py"):
            findings.extend(decision.findings)
    assert "proportionality" not in {f.subject for f in findings}
    state = guard.workspace(repo).task_state(None, "s1")
    assert state.spec.complexity.depth is None and state.spec.expected_scope == []


def test_the_implicit_task_is_persisted_and_tagged(guard, repo):
    _edit(guard, repo, COVERED)
    ws = guard.workspace(repo)
    task_id = ws.store.current_task_id("s1")
    row = ws.store.db.query("SELECT prompt, depth, spec FROM tasks WHERE id=?", (task_id,))[0]
    assert (row["prompt"], row["depth"]) == ("", "implicit")
    assert '"implicit": true' in row["spec"]


def test_a_store_that_cannot_record_still_gets_a_task(guard, repo, monkeypatch):
    ws = guard.workspace(repo)
    monkeypatch.setattr(ws.store, "create_task", lambda *a, **k: None)
    _edit(guard, repo, COVERED)
    state = ws.task_state(None, "s1")
    assert state is not None and state.task_id.startswith("mem-")
    assert guard.handle(_event(repo, EventType.STOP)).action is DecisionAction.BLOCK


def test_a_prompt_whose_task_cannot_be_stored_keeps_its_spec(guard, repo, monkeypatch):
    ws = guard.workspace(repo)
    monkeypatch.setattr(ws.store, "create_task", lambda *a, **k: None)
    guard.handle(
        AgentEvent(
            event=EventType.USER_PROMPT,
            agent="other-host",
            workspace=str(repo),
            session_id="s1",
            prompt_text="Fix the paginate helper. Do not run tests.",
        )
    )
    state = ws.task_state(None, "s1")
    assert state.task_id.startswith("mem-") and state.spec.tests_waived
    _edit(guard, repo, COVERED)
    assert ws.task_state(None, "s1") is state
    assert guard.handle(_event(repo, EventType.STOP)).action is DecisionAction.ALLOW


def test_a_read_opens_no_task(guard, repo):
    guard.handle(_event(repo, EventType.POST_TOOL_USE, "Read", file_path=COVERED))
    assert guard.workspace(repo).task_state(None, "s1") is None


def test_a_later_prompt_opens_a_real_task(guard, repo):
    _edit(guard, repo, COVERED)
    implicit = guard.workspace(repo).task_state(None, "s1")
    guard.handle(
        AgentEvent(
            event=EventType.USER_PROMPT,
            agent="other-host",
            workspace=str(repo),
            session_id="s1",
            prompt_text="Now rename paginate.",
        )
    )
    current = guard.workspace(repo).task_state(None, "s1")
    assert current.task_id != implicit.task_id and current.spec.prompt == "Now rename paginate."
