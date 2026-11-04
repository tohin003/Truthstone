"""SQLite hygiene (R7): a busy database costs a dropped row, never a wedged store.

The failure this guards against was reproduced against the real engine: another process
held the write lock longer than `busy_timeout`, then committed. The write that timed out
left the shared connection inside a transaction, the next read pinned a WAL snapshot, and
from then on every write failed with SQLITE_BUSY_SNAPSHOT — no task, no challenge,
nothing persisted, until the daemon restarted. The first event under the lock took 6.3 s,
longer than the 5 s hook timeout.
"""

from __future__ import annotations

import shutil
import sqlite3
import textwrap
import time
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import ChallengeCategory, DecisionAction, FailureMode, Severity, Verdict
from agentguard.core.models import Decision, EvidenceRef, Finding
from agentguard.core.store import (
    HOT_BUSY_TIMEOUT_MS,
    MAINTENANCE_BUSY_TIMEOUT_MS,
    Database,
    ProjectStore,
)
from tests.conftest import pre_tool_use

FIXTURES = Path(__file__).parent / "fixtures"


class ExternalWriter:
    """Another connection holding the write lock, as a second process or CLI would."""

    def __init__(self, path: Path) -> None:
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.execute("BEGIN IMMEDIATE")
        # Commit something, so the store's snapshot really is stale afterwards.
        self.conn.execute(
            "INSERT INTO metrics(project_id, name, value, labels, ts) VALUES('x', 'external', 1, '{}', 0)"
        )

    def commit(self) -> None:
        self.conn.execute("COMMIT")
        self.conn.close()


def _finding(subject: str = "UserRepository.get_active_users") -> Finding:
    return Finding(
        category=ChallengeCategory.EVIDENCE,
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        failure_mode=FailureMode.HALLUCINATED_API,
        severity=Severity.HIGH,
        subject=subject,
        summary="Method not found in repository.",
        evidence=[EvidenceRef(source="ast", path="src/repositories/user.py", line=1)],
    )


def _count(store: ProjectStore, table: str) -> int:
    # A fresh connection: what another process (or the next daemon) would see.
    other = sqlite3.connect(str(store.db.path))
    try:
        return other.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        other.close()


def test_hot_path_busy_timeout_is_short(workspace):
    store = ProjectStore.for_workspace(workspace)
    assert HOT_BUSY_TIMEOUT_MS <= 100
    assert store.db.query("PRAGMA busy_timeout")[0][0] == HOT_BUSY_TIMEOUT_MS


def test_maintenance_waits_patiently_then_restores_the_hot_timeout(workspace):
    store = ProjectStore.for_workspace(workspace)
    with store.db._maintenance_window() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == MAINTENANCE_BUSY_TIMEOUT_MS
    store.db.maintain(force=True)
    assert store.db.query("PRAGMA busy_timeout")[0][0] == HOT_BUSY_TIMEOUT_MS


def test_maintenance_reclaims_every_free_page(workspace):
    """`PRAGMA incremental_vacuum` frees one page per step; it used to be stepped once."""
    store = ProjectStore.for_workspace(workspace)
    db = store.db
    assert db.query("PRAGMA auto_vacuum")[0][0] == 2  # incremental
    expired = time.time() - 400 * 86400
    with db.transaction() as tx:
        for i in range(2_000):
            tx.execute(
                "INSERT INTO metrics(project_id, name, value, labels, ts) VALUES(?, ?, 1, ?, ?)",
                (store.project_id, f"m{i}", "x" * 400, expired),
            )
    assert tx.committed

    removed = db.maintain(force=True)

    assert removed["metrics"] == 2_000
    assert db.query("PRAGMA freelist_count")[0][0] == 0


def test_full_vacuum_converts_a_database_created_without_auto_vacuum(isolated_home):
    path = isolated_home / "agentguard.db"
    legacy = sqlite3.connect(str(path))
    legacy.execute("PRAGMA journal_mode=WAL")  # the old order: WAL first, auto_vacuum ignored
    legacy.execute("PRAGMA auto_vacuum=INCREMENTAL")
    legacy.execute("CREATE TABLE legacy_marker(x)")
    legacy.commit()
    legacy.close()

    db = Database(path)
    try:
        assert db.query("PRAGMA auto_vacuum")[0][0] == 0
        db.retention.vacuum_threshold_mb = 0  # make this maintenance pass run its VACUUM
        db.maintain(force=True)
        assert db.query("PRAGMA auto_vacuum")[0][0] == 2
        assert db.query("PRAGMA busy_timeout")[0][0] == HOT_BUSY_TIMEOUT_MS
    finally:
        db.close()


def test_external_write_lock_does_not_wedge_store(workspace):
    store = ProjectStore.for_workspace(workspace)
    store.open_session("s1", "claude-code")

    writer = ExternalWriter(store.db.path)
    try:
        # Writes fail while the lock is held — and a read in between is exactly what
        # used to pin the stale snapshot.
        assert store.create_task("s1", "during the lock") is None
        assert store.current_task_id("s1") is None
        store.record_challenge("t-locked", "fp")
        assert store.record_event_and_decision(
            claude.to_event(pre_tool_use()), Decision(action=DecisionAction.ALLOW)
        ) == ""
        assert not store.db._conn.in_transaction, "a failed write must not leave a transaction open"
    finally:
        writer.commit()

    task_id = store.create_task("s1", "after the lock")
    assert task_id
    assert store.current_task_id("s1") == task_id
    store.record_challenge(task_id, "fp-after")
    assert store.challenge_count(task_id, "fp-after") == 1
    assert store.record_event_and_decision(
        claude.to_event(pre_tool_use()), Decision(action=DecisionAction.CHALLENGE, findings=[_finding()])
    )
    # Durable, not just visible to the store's own connection.
    assert _count(store, "tasks") == 1
    assert _count(store, "challenges") == 1
    assert _count(store, "decisions") == 1
    assert store.db.failure_count >= 3
    assert "busy" in store.db.last_failure.lower() or "locked" in store.db.last_failure.lower()


def test_external_write_lock_does_not_disable_challenges(tmp_path):
    """End to end: after the lock is released, a task exists and the challenge fires."""
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        assert ws.index.ready(timeout=30)

        def event(name: str, **extra) -> object:
            payload = {
                "session_id": "s1",
                "transcript_path": "/t",
                "cwd": str(repo),
                "permission_mode": "default",
                "hook_event_name": name,
                **extra,
            }
            return claude.to_event(payload)

        guard.handle(event("SessionStart", source="startup"))
        writer = ExternalWriter(ws.store.db.path)
        try:
            for i in range(3):
                started = time.perf_counter()
                guard.handle(
                    event(
                        "PreToolUse",
                        tool_name="Edit",
                        tool_input={
                            "file_path": str(repo / "src/shop/models.py"),
                            "old_string": "a",
                            "new_string": f"b{i}",
                        },
                    )
                )
                # Two writes per event at <=100 ms each; the old 3 s timeout took 6.3 s.
                assert time.perf_counter() - started < 1.0
        finally:
            writer.commit()

        guard.handle(event("UserPromptSubmit", prompt="Add an active users report"))
        task_id = ws.store.current_task_id("s1")
        assert task_id, "a task must be created once the lock is released"
        assert _count(ws.store, "tasks") == 1

        hallucinated = textwrap.dedent(
            """\
            from shop.repositories.user import UserRepository


            def report(session):
                return UserRepository(session).get_active_users()
            """
        )
        decision = guard.handle(
            event(
                "PreToolUse",
                tool_name="Write",
                tool_input={"file_path": str(repo / "src/shop/api/report.py"), "content": hallucinated},
            )
        )
        assert decision.action == DecisionAction.CHALLENGE
        assert ws.store.challenge_count(task_id) == 1
    finally:
        guard.close()


def test_locked_db_bounds_write_latency(workspace):
    store = ProjectStore.for_workspace(workspace)
    store.open_session("s1", "claude-code")
    event = claude.to_event(pre_tool_use())
    attempts = {
        "record_event": lambda: store.record_event(event),
        "record_decision": lambda: store.record_decision(event, Decision()),
        "record_event_and_decision": lambda: store.record_event_and_decision(
            event, Decision(findings=[_finding()])
        ),
        "create_task": lambda: store.create_task("s1", "prompt"),
        "record_challenge": lambda: store.record_challenge("t", "fp"),
        "close_session": lambda: store.close_session("s1"),
    }

    writer = ExternalWriter(store.db.path)
    try:
        timings = {}
        for name, attempt in attempts.items():
            started = time.perf_counter()
            attempt()
            timings[name] = (time.perf_counter() - started) * 1000
    finally:
        writer.commit()

    slow = {name: round(ms) for name, ms in timings.items() if ms >= 300}
    assert not slow, f"write attempts under an external lock must give up quickly: {slow}"
    # And they really did give up rather than slipping through.
    assert _count(store, "events") == 0
    assert _count(store, "decisions") == 0
    assert _count(store, "tasks") == 0


def test_record_event_and_decision_is_atomic(workspace):
    store = ProjectStore.for_workspace(workspace)
    event = claude.to_event(pre_tool_use())
    decision = Decision(action=DecisionAction.CHALLENGE, reason="why", findings=[_finding(), _finding("B.c")])

    # Make the *last* statement of the group fail, after the event and decision inserts.
    store.db.write(
        "CREATE TRIGGER refuse_findings BEFORE INSERT ON findings "
        "BEGIN SELECT RAISE(ABORT, 'findings refused'); END",
        (),
    )
    assert store.record_event_and_decision(event, decision) == ""
    assert _count(store, "events") == 0, "the event must not outlive its failed decision"
    assert _count(store, "decisions") == 0
    assert _count(store, "findings") == 0
    assert not store.db._conn.in_transaction

    store.db.write("DROP TRIGGER refuse_findings", ())
    decision_id = store.record_event_and_decision(event, decision)
    assert decision_id
    detail = store.decision_detail(decision_id)
    assert detail["event_id"] == event.event_id
    assert len(detail["findings"]) == 2
    assert _count(store, "events") == 1


def test_record_event_and_decision_reports_disabled_writes(workspace, monkeypatch):
    store = ProjectStore.for_workspace(workspace)
    monkeypatch.setattr(type(store.db), "free_megabytes", lambda self: 1.0)
    assert store.record_event_and_decision(claude.to_event(pre_tool_use()), Decision()) == ""
    assert _count(store, "decisions") == 0


def test_transaction_is_nest_safe_and_never_raises(workspace):
    store = ProjectStore.for_workspace(workspace)
    db = store.db
    insert = "INSERT INTO metrics(project_id, name, value, labels, ts) VALUES(?, ?, 1, '{}', 0)"

    with db.transaction() as outer:
        outer.execute(insert, (store.project_id, "outer-before"))
        with db.transaction() as inner:
            inner.execute(insert, (store.project_id, "inner"))
            inner.execute("INSERT INTO no_such_table VALUES(1)")
        assert not inner.committed and inner.error is not None
        with db.transaction() as sibling:
            sibling.execute(insert, (store.project_id, "sibling"))
        assert sibling.committed
        outer.execute(insert, (store.project_id, "outer-after"))
    assert outer.committed
    names = {row["name"] for row in db.query("SELECT name FROM metrics")}
    assert names == {"outer-before", "sibling", "outer-after"}, "only the failed inner work is undone"

    with db.transaction() as failing:
        failing.execute(insert, (store.project_id, "doomed"))
        raise ValueError("a bug in the caller")  # swallowed: the hot path never sees it
    assert not failing.committed
    assert isinstance(failing.error, ValueError)
    assert not db.query("SELECT 1 FROM metrics WHERE name='doomed'")
    assert not db._conn.in_transaction
    assert db._tx_depth == 0


def test_transaction_interrupts_roll_back_and_propagate(workspace):
    store = ProjectStore.for_workspace(workspace)
    insert = "INSERT INTO metrics(project_id, name, value, labels, ts) VALUES(?, 'interrupted', 1, '{}', 0)"
    with pytest.raises(KeyboardInterrupt), store.db.transaction() as tx:
        tx.execute(insert, (store.project_id,))
        raise KeyboardInterrupt
    assert not store.db.query("SELECT 1 FROM metrics WHERE name='interrupted'")
    assert not store.db._conn.in_transaction


def test_session_rekey_migration_is_one_transaction(isolated_home):
    """The primary-key widening still migrates old databases, now atomically."""
    path = isolated_home / "agentguard.db"
    legacy = sqlite3.connect(str(path))
    legacy.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, agent TEXT NOT NULL, "
        "started_at REAL NOT NULL, ended_at REAL, meta TEXT NOT NULL DEFAULT '{}');"
        "CREATE INDEX idx_sessions_project ON sessions(project_id, started_at);"
        "INSERT INTO sessions(id, project_id, agent, started_at) VALUES('s1', 'p', 'claude-code', 1.0);"
    )
    legacy.commit()
    legacy.close()

    db = Database(path)
    try:
        ddl = db.query("SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'")[0]["sql"]
        assert "PRIMARY KEY (id, project_id)" in ddl
        assert [row["id"] for row in db.query("SELECT id FROM sessions")] == ["s1"]
        assert not db.query("SELECT 1 FROM sqlite_master WHERE name='sessions_legacy'")
        index = db.query("SELECT tbl_name FROM sqlite_master WHERE name='idx_sessions_project'")
        assert index[0]["tbl_name"] == "sessions"
    finally:
        db.close()
