"""R1 (engine): guarding never depends on persistence.

The challenge ledger read its counts back from the database on every admission, so a
store that could not write — critical disk, a degraded or corrupted database — read back
0 every time, and the same challenge was raised on every repetition (5 of 5 in D3's
probe, 3 of 3 in D6's). The ledger's in-memory counters are now authoritative, seeded from
the store and mirrored to it best-effort.
"""

from __future__ import annotations

import os
import shutil
import textwrap
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import DecisionAction
from agentguard.core.store import Database

FIXTURES = Path(__file__).parent / "fixtures"
REPORT = textwrap.dedent(
    """\
    from shop.repositories.user import UserRepository


    def report(session):
        return UserRepository(session).get_active_users()
    """
)
FAIL = "F.\n=== FAILURES ===\nE   assert 0 == 1\n=== 1 failed, 1 passed in 0.12s ===\n"


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


class Session:
    def __init__(self, guard: Guard, repo: Path) -> None:
        self.guard, self.repo = guard, repo

    def send(self, name: str, **fields):
        payload = {"session_id": "s", "cwd": str(self.repo), "hook_event_name": name, **fields}
        return self.guard.handle(claude.to_event(payload))

    def write_report(self):
        target = str(self.repo / "src/shop/api/report.py")
        return self.send("PreToolUse", tool_name="Write", tool_input={"file_path": target, "content": REPORT})

    def edit(self, path: str):
        full = self.repo / path
        full.write_text(full.read_text() + "\n# edited\n")
        arguments = {"file_path": str(full), "old_string": "a", "new_string": "b"}
        tool = {"tool_name": "Edit", "tool_input": arguments}
        return self.send("PostToolUse", tool_response={"filePath": str(full)}, **tool)


def test_challenge_raised_once_with_writes_disabled(repo, monkeypatch):
    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        assert ws.index.ready(timeout=30)
        # Critical free space: the store stops writing (SPEC §8), guarding continues.
        monkeypatch.setattr(Database, "free_megabytes", lambda self: 1.0)
        assert not ws.store.db.writes_enabled
        session = Session(guard, repo)
        session.send("UserPromptSubmit", prompt="Add an active users report")

        decisions = [session.write_report().action for _ in range(3)]
        assert decisions == [DecisionAction.CHALLENGE, DecisionAction.ALLOW, DecisionAction.ALLOW]
        task_id = ws.resolve_task_id("s")
        assert ws.ledger.challenge_count(task_id) == 1
        assert ws.store.challenge_count(task_id) == 0, "nothing was persisted"
    finally:
        guard.close()


def test_guards_with_corrupted_database(isolated_home, repo):
    path = isolated_home / "agentguard.db"
    path.write_bytes(b"this is not a sqlite database" * 200)
    os.chmod(path, 0o600)

    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        assert ws.store.degraded_reason
        assert ws.index.ready(timeout=30)
        session = Session(guard, repo)
        session.send("SessionStart", source="startup")
        session.send("UserPromptSubmit", prompt="Fix paginate so page 0 is page 1.")

        # The hallucinated method is challenged, once.
        assert session.write_report().action is DecisionAction.CHALLENGE
        assert session.write_report().action is DecisionAction.ALLOW

        # The completion gate still sees the task: an edit and a failing run.
        session.edit("src/shop/utils/pagination.py")
        held = session.send("Stop", last_assistant_message="Done.", stop_hook_active=False)
        assert held.action is DecisionAction.BLOCK and "tests/test_pagination.py" in held.reason
        bash = {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}}
        session.send("PostToolUseFailure", error=f"Exit code 1\n{FAIL}", **bash)
        failing = session.send("Stop", last_assistant_message="All tests pass.", stop_hook_active=False)
        assert failing.action is DecisionAction.BLOCK and "reported failures" in failing.reason
        assert path.read_bytes().startswith(b"this is not a sqlite database"), "never overwritten"
    finally:
        guard.close()
