"""R7 (wiring): one transaction per event.

`Guard.handle` recorded an event and then its decision as separate writes: two or more
commits per event, and a failure between them left an event whose decision was lost. It
now records both, with the findings, through `ProjectStore.record_event_and_decision`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import DecisionAction

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    assert g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


def _read(repo: Path, tool_use_id: str = "r1"):
    return claude.to_event(
        {
            "session_id": "sess-1",
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": str(repo / "src/shop/models.py")},
            "tool_response": {"type": "text"},
            "tool_use_id": tool_use_id,
        }
    )


def _count(store, table: str) -> int:
    return store.db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


class Commits:
    """Counts what the shared connection commits: explicit COMMITs, plus each write that
    ran outside a transaction (autocommit — what `Database.write` alone does)."""

    def __init__(self, store) -> None:
        self.count = 0
        self._in_tx = False
        store.db._conn.set_trace_callback(self._statement)
        self._conn = store.db._conn

    def _statement(self, sql: str) -> None:
        head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if head == "BEGIN":
            self._in_tx = True
        elif head in ("COMMIT", "END"):
            self._in_tx = False
            self.count += 1
        elif head == "ROLLBACK":
            self._in_tx = False
        elif head in ("INSERT", "UPDATE", "DELETE", "REPLACE") and not self._in_tx:
            self.count += 1

    def close(self) -> None:
        self._conn.set_trace_callback(None)


def test_a_normal_event_makes_exactly_one_commit(guard, repo):
    ws = guard.workspace(repo)
    start = {"session_id": "sess-1", "cwd": str(repo), "hook_event_name": "SessionStart"}
    guard.handle(claude.to_event(start))
    commits = Commits(ws.store)
    try:
        event = _read(repo)
        decision = guard.handle(event)
    finally:
        commits.close()
    assert decision.action is DecisionAction.ALLOW
    assert commits.count == 1
    detail = ws.store.decision_detail(decision.decision_id)
    assert detail is not None and detail["event_id"] == event.event_id, "the id is the persisted one"


def test_a_failed_write_leaves_neither_the_event_nor_the_decision(guard, repo):
    ws = guard.workspace(repo)
    ws.store.db.write(
        "CREATE TRIGGER refuse_decisions BEFORE INSERT ON decisions "
        "BEGIN SELECT RAISE(ABORT, 'decisions refused'); END",
        (),
    )
    events_before = _count(ws.store, "events")
    decision = guard.handle(_read(repo))  # never raises
    assert decision.action is DecisionAction.ALLOW
    assert _count(ws.store, "events") == events_before, "no event without its decision"
    assert _count(ws.store, "decisions") == 0
    assert decision.decision_id == "", "an id is only set when the decision was persisted"
    assert not ws.store.db._conn.in_transaction

    ws.store.db.write("DROP TRIGGER refuse_decisions", ())
    again = guard.handle(_read(repo, "r2"))
    assert again.decision_id and _count(ws.store, "decisions") == 1
