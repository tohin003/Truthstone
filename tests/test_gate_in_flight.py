"""G7: test runs still in flight at Stop.

Claude Code's Stop payload lists the background tasks still running (captured live:
`tests/fixtures/hook_payloads/Stop.background_tasks.json`). It used to be ignored, so a
backgrounded `pytest` that had not finished passed as "seen but unreadable" (D4b F6).
Now a running shell task whose command is a recognised test or typecheck run holds the
turn; anything else (`sleep 25`, a watch mode) is not a result anyone is waiting for.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.test_gate_timeline import PASS, Session
from truthstone.adapters.claude_code import translate as claude

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_STOP = json.loads((FIXTURES / "hook_payloads" / "Stop.background_tasks.json").read_text())


@pytest.fixture
def session(tmp_path):
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    s = Session(repo)
    yield s
    s.close()


def _stop_with(command: str, status: str = "running") -> dict:
    """The live payload, with its one background task running `command`."""
    task = {**LIVE_STOP["background_tasks"][0], "command": command, "status": status}
    return {**LIVE_STOP, "session_id": "sess-1", "background_tasks": [task]}


def test_the_live_payload_translates_to_pending_tasks():
    event = claude.to_event(LIVE_STOP)
    assert event.pending_tasks == [
        {"id": "bajc5zwrv", "type": "shell", "status": "running", "command": "sleep 25"}
    ]
    quiet = json.loads((FIXTURES / "hook_payloads" / "Stop.json").read_text())
    assert claude.to_event(quiet).pending_tasks == []


def test_malformed_background_tasks_are_dropped():
    payload = {**LIVE_STOP, "background_tasks": ["pytest", {"command": 3, "status": "running"}, None]}
    assert claude.to_event(payload).pending_tasks == [{"status": "running"}]
    assert claude.to_event({**LIVE_STOP, "background_tasks": "pytest"}).pending_tasks == []


def test_a_running_test_task_holds_the_turn(session):
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    held = session.send(_stop_with("pytest -q tests/"))
    assert held["decision"] == "block"
    assert "still running in the background" in held["reason"]
    assert "`pytest -q tests/`" in held["reason"]


def test_a_running_typecheck_holds_the_turn(session):
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    held = session.send(_stop_with("npx tsc --noEmit"))
    assert held["decision"] == "block"


def test_the_live_payload_as_captured_is_not_a_test_run(session):
    """`sleep 25` is running, but nobody is waiting on it for a verdict."""
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    assert session.send({**LIVE_STOP, "session_id": "sess-1"}) == {}


@pytest.mark.parametrize("command", ["npx vitest watch", "npx jest --watch", "npm run test:watch"])
def test_a_watch_mode_is_ignored(session, command):
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    assert session.send(_stop_with(command)) == {}


def test_a_finished_task_is_not_in_flight(session):
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    assert session.send(_stop_with("pytest -q", status="completed")) == {}


def test_a_background_launch_is_pending_not_an_unreadable_run(session):
    """`run_in_background`: the PostToolUse result is a task id, not test output."""
    session.prompt()
    session.edit()
    session.send(
        {
            "session_id": "sess-1",
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q", "run_in_background": True},
            "tool_response": {"stdout": "", "stderr": "", "interrupted": False, "backgroundTaskId": "b1"},
        }
    )
    verification = session.state().verification
    assert [run.command for run in verification.background] == ["pytest -q"]
    assert verification.commands_seen == [] and verification.inconclusive == []
    held = session.send(_stop_with("pytest -q"))
    assert held["decision"] == "block" and "still running" in held["reason"]


def test_a_shell_backgrounded_run_finished_unseen_is_not_held(session):
    """`pytest > log &` returned at once; at Stop the host lists nothing running, and the
    result was never seen here. Could not tell is never failed."""
    session.prompt()
    session.edit()
    session.run("pytest -q > /tmp/log 2>&1 &", "")
    assert session.state().verification.background
    assert session.stop() == {}
