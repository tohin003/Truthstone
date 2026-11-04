"""The store never raises at construction (R1): a broken database degrades, loudly.

Reproduced before the change (x_corrupt.py): a corrupted ``agentguard.db`` made
`Database.shared()` raise, so `Workspace.__init__` raised, so no workspace existed at all —
AgentGuard was fully inert, and `doctor` crashed. Persistence is never supposed to be a
dependency of guarding.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

import agentguard.core.store as store_module
from agentguard.adapters.claude_code import translate as claude
from agentguard.cli.main import app
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import DecisionAction
from agentguard.core.models import Decision
from agentguard.core.store import Database, ProjectStore
from tests.conftest import pre_tool_use

FIXTURES = Path(__file__).parent / "fixtures"
GARBAGE = b"this is not a sqlite database" * 200


def _corrupt(home: Path) -> Path:
    path = home / "agentguard.db"
    path.write_bytes(GARBAGE)
    os.chmod(path, 0o600)
    return path


def _degraded_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "persistence is off" in r.getMessage()]


def test_corrupted_database_yields_degraded_store_not_exception(isolated_home, workspace):
    path = _corrupt(isolated_home)

    store = ProjectStore.for_workspace(workspace)  # used to raise sqlite3.DatabaseError

    assert store.degraded_reason
    assert store.db.degraded
    # Writes are no-ops, and say so where a caller can tell.
    event = claude.to_event(pre_tool_use())
    assert store.record_event_and_decision(event, Decision(action=DecisionAction.CHALLENGE)) == ""
    insert = "INSERT INTO metrics(project_id, name, value, ts) VALUES('p', 'n', 1, 0)"
    assert store.db.write(insert, ()) is False
    store.open_session("s1", "claude-code")
    store.record_event(event)
    store.record_challenge("t", "fp")
    store.finish_verification(store.start_verification("t", "pytest"), "passed", {})
    store.close_session("s1")
    # Queries answer "nothing", never raise.
    assert store.current_task_id("s1") is None
    assert store.recent_decisions() == []
    assert store.decision_detail("x") is None
    assert store.challenge_count("t") == 0
    assert store.failure_mode_counts(0.0) == []
    assert store.activity(0.0)["sessions"] == 0
    assert store.db.query("SELECT 1") == []
    assert store.db.maintain(force=True) == {}
    stats = store.db.stats()
    assert stats["degraded_reason"] == store.degraded_reason
    assert stats["writes_enabled"] is False
    # The broken file is evidence for the developer: never overwritten or deleted.
    assert path.read_bytes() == GARBAGE


def test_guarding_survives_a_corrupted_database(isolated_home, tmp_path):
    """The point of R1: the hallucinated Write is still challenged."""
    _corrupt(isolated_home)
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)

    def event(name: str, **extra):
        payload = {
            "session_id": "c",
            "transcript_path": "/t",
            "cwd": str(repo),
            "permission_mode": "default",
            "hook_event_name": name,
            **extra,
        }
        return claude.to_event(payload)

    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)  # used to raise: no workspace, nothing guarded
        assert ws.store.degraded_reason
        assert ws.index.ready(timeout=30)
        guard.handle(event("SessionStart", source="startup"))
        guard.handle(event("UserPromptSubmit", prompt="Add an active users report"))
        content = textwrap.dedent(
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
                tool_input={"file_path": str(repo / "src/shop/api/report.py"), "content": content},
            )
        )
        assert decision.action == DecisionAction.CHALLENGE
    finally:
        guard.close()


@pytest.mark.parametrize("cause", ["corrupted", "directory", "symlink"])
def test_degraded_store_reports_reason(isolated_home, workspace, tmp_path, caplog, cause):
    path = isolated_home / "agentguard.db"
    if cause == "corrupted":
        _corrupt(isolated_home)
        expected = ("corrupted", "mv ")
    elif cause == "directory":
        path.mkdir()
        expected = ("non-regular",)
    else:
        target = tmp_path / "elsewhere.db"
        target.write_bytes(b"")
        path.symlink_to(target)
        expected = ("symlink",)

    caplog.set_level(logging.WARNING, logger="agentguard.core.store")
    store = ProjectStore.for_workspace(workspace)
    for _ in range(3):  # more handles, more failed writes: still one report
        ProjectStore.for_workspace(workspace).create_task("s1", "prompt")
        store.record_event_and_decision(claude.to_event(pre_tool_use()), Decision())

    reason = store.degraded_reason
    assert reason == Database.shared().degraded_reason
    assert str(path) in reason
    for fragment in expected:
        assert fragment in reason
    assert len(_degraded_warnings(caplog)) == 1, "logged once, not per call"


def test_degraded_database_reopens_in_place_once_repaired(isolated_home, workspace, monkeypatch):
    path = _corrupt(isolated_home)
    store = ProjectStore.for_workspace(workspace)
    assert store.degraded_reason

    path.unlink()  # the developer moved it aside, as the reason suggests
    monkeypatch.setattr(store_module, "_REOPEN_INTERVAL_S", 0.0)
    assert Database.shared() is store.db

    assert store.degraded_reason == ""
    task_id = store.create_task("s1", "after the repair")
    assert store.current_task_id("s1") == task_id, "existing handles share the reopened database"


def test_reopen_is_rate_limited(isolated_home, workspace):
    _corrupt(isolated_home)
    store = ProjectStore.for_workspace(workspace)
    assert store.db.reopen_due() is False  # just failed: wait before trying again
    assert store.db.reopen() is False
    assert store.degraded_reason


def test_corruption_found_at_runtime_degrades_the_store(workspace, caplog):
    store = ProjectStore.for_workspace(workspace)
    assert not store.degraded_reason
    caplog.set_level(logging.WARNING, logger="agentguard.core.store")

    store.db._after_error("record_event", sqlite3.DatabaseError("database disk image is malformed"))

    assert "corrupted" in store.degraded_reason
    assert store.db.write("SELECT 1", ()) is False
    assert len(_degraded_warnings(caplog)) == 1


def test_unusable_home_yields_degraded_store(workspace, monkeypatch):
    def no_home():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(store_module, "database_path", no_home)
    store = ProjectStore.for_workspace(workspace)
    assert "no usable AgentGuard home" in store.degraded_reason
    assert store.db.reopen() is False
    assert store.current_task_id("s1") is None


def test_project_identity_failure_falls_back_to_the_path(workspace, monkeypatch):
    def broken(root):
        raise OSError("git exploded")

    monkeypatch.setattr(store_module, "project_identity", broken)
    store = ProjectStore.for_workspace(workspace)
    assert store.identity.root == str(workspace)
    assert store.project_id
    task_id = store.create_task("s1", "still recorded")
    assert store.current_task_id("s1") == task_id


def test_cli_reports_degraded_storage(isolated_home, tmp_path, monkeypatch):
    from agentguard.adapters.codex import status

    monkeypatch.setattr(status, "codex_version", lambda executable=None: None)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.delenv("AGENTGUARD_PLUGIN_DATA", raising=False)
    (tmp_path / "project").mkdir()
    monkeypatch.chdir(tmp_path / "project")
    _corrupt(isolated_home)
    runner = CliRunner()

    stats = runner.invoke(app, ["db", "stats"])
    assert stats.exit_code == 0, stats.output
    assert "DISABLED (database unavailable)" in stats.output
    assert "corrupted" in stats.output

    doctor = runner.invoke(app, ["doctor"])
    assert doctor.exception is None or isinstance(doctor.exception, SystemExit), doctor.output
    assert "persistence is OFF" in doctor.output
    assert doctor.exit_code == 1
