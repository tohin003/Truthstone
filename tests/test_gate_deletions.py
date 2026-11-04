"""G5 (core): deletions and moves count as changes.

`TaskState.deleted_files` had no writer, and the index forgets a deleted file — and with
it which tests reached it — so deleting covered code looked like a change nothing tests,
and the gate passed (D5's probe: `rm` of a covered file, empty change set).

The Codex adapter maps a patch's `*** Delete File` to the core tool `Delete` and a move
to a Write of the destination plus a Delete of the source; these tests drive the live
fixtures through `handle_payload` and the real Guard. Deletions made through Bash
(`rm`, `git mv`) need a refreshed-delta API in the index and are not covered here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from truthstone.adapters.codex import translate as codex
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import EventType
from truthstone.core.events import AgentEvent

FIXTURES = Path(__file__).parent / "fixtures"
PAYLOADS = FIXTURES / "codex_payloads"
SESSION = "sess-codex"


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


@pytest.fixture
def guard(repo):
    g = Guard(Settings(profile="full"))
    g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


def _payload(repo: Path, hook: str, **fields) -> dict:
    return {"session_id": SESSION, "turn_id": "t1", "cwd": str(repo), "hook_event_name": hook, **fields}


def _prompt(guard, repo: Path, text: str = "Tidy up the utils package.") -> None:
    codex.handle_payload(guard, _payload(repo, "UserPromptSubmit", prompt=text))


def _live(name: str, repo: Path) -> dict:
    payload = json.loads((PAYLOADS / f"{name}.json").read_text())
    return {**payload, "session_id": SESSION, "cwd": str(repo)}


def _state(guard, repo: Path):
    return guard.workspace(repo).task_state(None, SESSION)


def test_codex_patch_delete_populates_deleted_files(guard, repo):
    _prompt(guard, repo)
    (repo / "b.txt").write_text("bee\n")  # what Codex's patch did on disk
    codex.handle_payload(guard, _live("PostToolUse.apply_patch.add_delete", repo))
    state = _state(guard, repo)
    assert state.deleted_files == {"old.txt"}
    assert {"b.txt", "old.txt"} <= state.changed_files
    assert state.last_change_seq["old.txt"] > state.last_change_seq["b.txt"]


def test_move_counts_both_paths(guard, repo):
    _prompt(guard, repo)
    (repo / "d.txt").write_text("see\n")
    codex.handle_payload(guard, _live("PostToolUse.apply_patch.move", repo))
    state = _state(guard, repo)
    assert {"c.txt", "d.txt"} <= state.changed_files
    assert state.deleted_files == {"c.txt"}


def test_deleted_covered_file_needs_tests(guard, repo):
    """D5's probe, through Codex: the patch deletes code that tests/test_pagination.py
    imports. Nothing is run, and "Done." is held — naming the test that covered it."""
    _prompt(guard, repo, "Remove the old pagination helper.")
    patch = "*** Begin Patch\n*** Delete File: src/shop/utils/pagination.py\n*** End Patch"
    tool = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "tool_use_id": "c1"}
    assert codex.handle_payload(guard, _payload(repo, "PreToolUse", **tool)) == {}
    (repo / "src/shop/utils/pagination.py").unlink()
    codex.handle_payload(guard, _payload(repo, "PostToolUse", tool_response="Success.", **tool))

    state = _state(guard, repo)
    assert state.deleted_files == {"src/shop/utils/pagination.py"}
    assert "tests/test_pagination.py" in state.deleted_coverage["src/shop/utils/pagination.py"]
    assert "src/shop/utils/pagination.py" not in guard.workspace(repo).index.files

    held = codex.handle_payload(
        guard, _payload(repo, "Stop", stop_hook_active=False, last_assistant_message="Done.")
    )
    assert held["decision"] == "block"
    assert "tests/test_pagination.py" in held["reason"]


def test_a_deleted_then_rewritten_file_is_not_deleted(guard, repo):
    _prompt(guard, repo)
    target = repo / "src/shop/utils/pagination.py"
    for tool in ("Delete", "Write"):
        if tool == "Delete":
            target.unlink()
        else:
            target.write_text("def paginate():\n    return []\n")
        guard.handle(
            AgentEvent(
                event=EventType.POST_TOOL_USE,
                agent="codex",
                workspace=str(repo),
                session_id=SESSION,
                tool=tool,
                arguments={"file_path": str(target)},
            )
        )
    state = _state(guard, repo)
    assert state.deleted_files == set()
    assert "src/shop/utils/pagination.py" in state.touched_files


def test_a_delete_is_a_mutating_action():
    event = AgentEvent(event=EventType.PRE_TOOL_USE, tool="Delete", arguments={"file_path": "x.py"})
    assert event.is_mutating and event.is_delete and not event.is_read_only
