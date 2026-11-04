"""Everything needed to rebuild a task after a daemon restart is in the store (R14).

TaskState lives only in the engine's memory. After a restart mid-task (or an eviction
from its window of eight) Stop after failing tests returned allow: the new daemon knew
nothing of the edits or the failing run. The rows were there all along — the task, its
post-tool events (whose arguments keep the path) and its verifications. `task_record` and
`task_activity` return them, bounded and in order. The engine's rebuild is separate work.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import EventType
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision
from agentguard.core.store import ProjectStore
from tests.conftest import user_prompt_submit

FIXTURES = Path(__file__).parent / "fixtures"
PATH_KEYS = ("file_path", "notebook_path")  # Claude Code's; the caller names them
FAIL = "F.\n=== FAILURES ===\nE   assert 0 == 1\n=== 1 failed, 1 passed in 0.12s ===\n"
PASS = "..\n=== 2 passed in 0.10s ===\n"
# Thirty 190-character values: the arguments' JSON is cut at its 4,000-byte row limit.
BULK = {f"k{i}": "v" * 190 for i in range(30)}


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


class Session:
    """Claude-Code-shaped payloads through the real adapter and the real Guard."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.guard = Guard(Settings())
        self.guard.workspace(repo).index.ready(timeout=30)

    def send(self, payload: dict) -> None:
        self.guard.handle(claude.to_event({"session_id": "sess-1", **payload, "cwd": str(self.repo)}))

    def edit(self, path: str, tool: str = "Edit") -> None:
        full = self.repo / path
        full.write_text(full.read_text() + "\n# touched\n" if full.exists() else "x = 1\n")
        self.send(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": tool,
                "tool_input": {"file_path": str(full), "old_string": "a", "new_string": "b"},
                "tool_response": {"filePath": str(full)},
            }
        )

    def pytest(self, output: str, exit_code: int) -> None:
        if exit_code == 0:
            payload = {"hook_event_name": "PostToolUse", "tool_response": {"stdout": output, "stderr": ""}}
        else:
            payload = {"hook_event_name": "PostToolUseFailure", "error": f"Exit code {exit_code}\n{output}"}
        self.send({**payload, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}})


def test_task_activity_reconstructs_touched_files_and_outcomes(repo):
    session = Session(repo)
    try:
        session.send(user_prompt_submit("Fix the paginate helper so page 0 is page 1."))
        session.edit("src/shop/utils/pagination.py")
        session.pytest(FAIL, exit_code=1)
        session.edit("src/shop/models.py")
        read = {"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "x"}}
        session.send(read)
        session.pytest(PASS, exit_code=0)
        session.edit("src/shop/utils/pagination.py")
        task_id = session.guard.workspace(repo).resolve_task_id("sess-1")
    finally:
        session.guard.close()  # the daemon "restarts": nothing in memory survives

    store = ProjectStore.for_workspace(repo)
    record = store.task_record(task_id)
    assert record["session_id"] == "sess-1"
    assert record["prompt"] == "Fix the paginate helper so page 0 is page 1."
    assert record["spec_complete"] and record["spec"]["prompt"] == record["prompt"]
    assert record["created_at"] <= time.time() and record["status"] == "open"

    activity = store.task_activity(task_id, PATH_KEYS, change_tools={"Edit", "Write", "MultiEdit"})
    pagination, models = (str(repo / p) for p in ("src/shop/utils/pagination.py", "src/shop/models.py"))
    assert [c["path"] for c in activity["changes"]] == [pagination, models, pagination]
    assert activity["touched"] == [pagination, models]
    assert activity["deleted"] == []
    runs = activity["verifications"]
    assert [r["status"] for r in runs] == ["failed", "passed"]
    assert runs[0]["kind"] == "pytest" and runs[0]["detail"]["command"] == "pytest -q"
    assert "1 failed" in runs[0]["detail"]["summary"] and runs[0]["detail"]["failed"] == 1
    # The order G2a's timeline needs: edit, fail, edit, pass, edit.
    assert [(e["kind"], e["index"]) for e in activity["timeline"]] == [
        ("change", 0), ("verification", 0), ("change", 1), ("verification", 1), ("change", 2),
    ]
    assert not activity["truncated"] and activity["skipped"] == 0

    every_tool = store.task_activity(task_id, PATH_KEYS)
    assert "x" in [c["path"] for c in every_tool["changes"]], "None means every tool, as the engine does"


def _event(task_id: str, tool: str, arguments: dict, ts: float, kind=EventType.POST_TOOL_USE) -> AgentEvent:
    return AgentEvent(
        event=kind, agent="codex", workspace="/w", session_id="s", task_id=task_id, tool=tool,
        arguments=arguments, ts=ts,
    )


def test_removals_bounds_and_cut_rows(repo):
    store = ProjectStore.for_workspace(repo)
    task_id = store.create_task("s", "tidy up", spec={"prompt": "tidy up"})
    base = time.time()
    events = [
        _event(task_id, "Write", {"file_path": "/w/new.py", "content": "x"}, base + 1),
        _event(task_id, "Delete", {"file_path": "/w/old.py"}, base + 2),
        # Arguments cut at the row limit: the JSON no longer parses, the path still reads.
        _event(task_id, "MultiEdit", {"file_path": "/w/big.py", **BULK}, base + 3),
        # A path longer than `summarize_value` keeps is no path at all.
        _event(task_id, "Write", {"file_path": "/w/" + "d" * 300}, base + 4),
        _event(task_id, "Edit", {"file_path": "/w/failed.py"}, base + 5, kind=EventType.POST_TOOL_FAILURE),
        _event(task_id, "Edit", {"file_path": "/w/before.py"}, base + 6, kind=EventType.PRE_TOOL_USE),
    ]
    for event in events:
        store.record_event_and_decision(event, Decision.allow())

    activity = store.task_activity(task_id, ("file_path",), removal_tools={"Delete"})
    assert activity["touched"] == ["/w/new.py", "/w/big.py", "/w/failed.py"], "post-tool events only"
    assert activity["deleted"] == ["/w/old.py"]
    assert [c["type"] for c in activity["changes"]][-1] == "post_tool_failure"
    assert activity["skipped"] == 1

    newest = store.task_activity(task_id, ("file_path",), max_events=2)
    assert newest["truncated"] and [c["path"] for c in newest["changes"]] == ["/w/failed.py"]

    for n in range(5):
        store.finish_verification(store.start_verification(task_id, "pytest"), "passed", {"n": n})
    runs = store.task_activity(task_id, ("file_path",), max_verifications=3)["verifications"]
    assert [r["detail"]["n"] for r in runs] == [2, 3, 4], "the newest runs, oldest first"


def test_concurrent_hooks_are_ordered_by_when_they_were_handled(repo):
    """An event's `ts` is when its payload was read. Two hooks in flight can be read in one
    order and handled in the other; the decision's time is the handling order."""
    store = ProjectStore.for_workspace(repo)
    task_id = store.create_task("s", "fix it")
    base = time.time()
    edit = _event(task_id, "Edit", {"file_path": "/w/a.py"}, base)  # read first ...
    run = store.start_verification(task_id, "pytest")  # ... but the run was handled first
    store.finish_verification(run, "failed", {"summary": "1 failed"})
    time.sleep(0.01)
    store.record_event_and_decision(edit, Decision.allow())  # handled after the run
    timeline = store.task_activity(task_id, ("file_path",))["timeline"]
    assert [entry["kind"] for entry in timeline] == ["verification", "change"]


def test_unknown_tasks_and_a_broken_store_answer_empty(repo, tmp_path, monkeypatch):
    store = ProjectStore.for_workspace(repo)
    assert store.task_record("no-such-task") is None
    empty = store.task_activity("no-such-task", ("file_path",))
    assert empty["changes"] == [] and empty["timeline"] == [] and not empty["truncated"]
    assert store.task_activity("", ("file_path",))["task_id"] == ""

    def broken(*args, **kwargs):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(store.db, "query", broken)
    assert store.task_record("t") is None
    assert store.task_activity("t", ("file_path",))["changes"] == []


def test_a_spec_cut_at_its_row_limit_is_reported_incomplete(repo):
    store = ProjectStore.for_workspace(repo)
    task_id = store.create_task("s", "big", spec={"targets": ["t" * 100 for _ in range(100)]})
    record = store.task_record(task_id)
    assert record["spec"] == {} and record["spec_complete"] is False
    assert json.loads(json.dumps(record))  # plain data, ready for the engine
