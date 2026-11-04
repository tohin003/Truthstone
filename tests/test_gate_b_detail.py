"""R14-detail: a recorded test run keeps the whole outcome, bounded.

`_record_test_run` stored ``{"command", "summary", "failed"}``. After a restart the engine
rebuilds the task's runs from that row, and G2a's timeline compares runs by family, key
and scope — none of which were stored. The row now carries every field the timeline
reads, capped below the store's own limits so that what comes back is what was written.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.conftest import user_prompt_submit
from truthstone.adapters.claude_code import translate as claude
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.store import ProjectStore
from truthstone.verify import runners

FIXTURES = Path(__file__).parent / "fixtures"
FAIL = (
    "F.\n=== FAILURES ===\nE   assert 0 == 1\n"
    "=== short test summary info ===\n"
    "FAILED tests/test_pagination.py::test_page_zero - assert 0 == 1\n"
    "=== 1 failed, 1 passed in 0.12s ===\n"
)
COMMAND = "uv run pytest -q tests/test_pagination.py -k zero 2>&1 | tail -20"
SCHEMA = {
    "command", "summary", "failed", "runner", "passed", "total", "exit_code", "family", "key",
    "scope", "failing_files",
}


def _send(guard: Guard, repo: Path, payload: dict) -> None:
    guard.handle(claude.to_event({"session_id": "sess-1", **payload, "cwd": str(repo)}))


def test_the_stored_row_round_trips_every_key(tmp_path):
    repo = Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))
    guard = Guard(Settings())
    try:
        guard.workspace(repo).index.ready(timeout=30)
        _send(guard, repo, user_prompt_submit("Fix the paginate helper so page 0 is page 1."))
        _send(
            guard,
            repo,
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "tool_input": {"command": COMMAND},
                "error": f"Exit code 1\n{FAIL}",
            },
        )
        ws = guard.workspace(repo)
        live = ws.task_state(None, "sess-1").verification.outcomes[-1]
        task_id = ws.resolve_task_id("sess-1")
    finally:
        guard.close()  # a restart: nothing in memory survives

    store = ProjectStore.for_workspace(repo)
    [row] = store.task_activity(task_id, ("file_path",))["verifications"]
    assert row["detail_complete"] and row["status"] == "failed"
    detail = row["detail"]
    assert set(detail) == SCHEMA
    assert detail == {
        "command": live.command,
        "summary": live.summary,
        "failed": live.failed,
        "runner": "pytest",
        "passed": False,
        "total": live.total,
        "exit_code": 1,  # what the host reported (through `tail`, so the text gave the verdict)
        "family": "python",
        "key": "pytest -q tests/test_pagination.py -k zero",
        "scope": ["-k=zero", "tests/test_pagination.py"],
        "failing_files": ["tests/test_pagination.py"],
    }

    rebuilt = runners.outcome_from_detail(detail, row["status"])
    for name in ("runner", "passed", "total", "failed", "summary", "command", "family", "key", "scope",
                 "failing_files", "exit_code"):
        assert getattr(rebuilt, name) == getattr(live, name), name
    # What G2a's same-run matching needs: the rebuilt run is "the same run" as the live one.
    assert runners.covers(rebuilt, live) and runners.covers(live, rebuilt)


def test_exit_status_is_kept_when_it_is_the_runners():
    outcome = runners.outcome_from_result("pytest -q", {"stdout": FAIL, "exit_code": 1})
    detail = runners.outcome_detail(outcome)
    assert detail["exit_code"] == 1 and detail["passed"] is False and detail["failed"] == 1
    assert runners.outcome_from_detail(json.loads(json.dumps(detail))).exit_code == 1


def test_long_values_are_capped_below_the_stores_limits(tmp_path):
    paths = " ".join(f"tests/t{i}/test_{'x' * 150}.py" for i in range(40))
    outcome = runners.parse_output(f"pytest {paths}", "")
    outcome.passed, outcome.summary = False, "s" * 900
    outcome.failing_files = tuple(f"tests/t{i}/test_{'y' * 300}.py" for i in range(40))
    detail = runners.outcome_detail(outcome)
    assert set(detail) == SCHEMA
    assert len(json.dumps(detail)) <= runners.DETAIL_BYTES
    assert all(len(value) <= runners.DETAIL_TEXT for value in detail.values() if isinstance(value, str))
    for name in ("scope", "failing_files"):
        assert 0 < len(detail[name]) <= runners.DETAIL_ITEMS
        assert all(len(item) <= runners.DETAIL_TEXT for item in detail[name])

    # Through the real store: the row reads back intact, with no truncation markers.
    store = ProjectStore.for_workspace(tmp_path)
    task_id = store.create_task("s", "fix it", spec={"prompt": "fix it"})
    store.finish_verification(store.start_verification(task_id, "pytest"), "failed", detail)
    [row] = store.task_activity(task_id, ())["verifications"]
    assert row["detail_complete"] and row["detail"] == detail


def test_old_rows_still_rebuild():
    """Rows written before R14-detail: the command is re-read, the status gives the verdict."""
    old = {"command": "pytest -q tests/test_pagination.py", "summary": "1 failed, 1 passed", "failed": 1}
    rebuilt = runners.outcome_from_detail(old, "failed")
    assert rebuilt.passed is False and rebuilt.runner == "pytest" and rebuilt.family == "python"
    assert rebuilt.key == "pytest -q tests/test_pagination.py"
    assert rebuilt.scope == ("tests/test_pagination.py",)
    assert runners.outcome_from_detail({"summary": "no command"}, "passed") is None
    assert runners.outcome_from_detail({"command": "pytest"}, "running") is None  # no verdict
