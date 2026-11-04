"""G9: SubagentStop never runs the parent task's gate.

Probe F: the parent edited covered code, then an Explore subagent finished — and was
told "incomplete ... run the tests", spending the parent's two-block budget. Latent for
Claude Code (the installer does not subscribe SubagentStop) but live for Codex, whose
subagents share the parent's session id. The verdict is still computed and recorded for
the census; it is never said, and `stop_blocks` is never spent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.test_gate_timeline import Session
from truthstone.adapters.codex import translate as codex

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path):
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    s = Session(repo)
    yield s
    s.close()


def _subagent_stop(message: str = "Found the pagination helper in src/shop/utils.") -> dict:
    return {
        "session_id": "sess-1",
        "hook_event_name": "SubagentStop",
        "stop_hook_active": False,
        "last_assistant_message": message,
    }


def test_subagent_stop_never_blocks_or_spends_budget(session):
    session.prompt()
    session.edit()  # covered code changed, no tests run: the parent's gate would block
    for _ in range(3):
        assert session.send(_subagent_stop()) == {}, "nothing reaches the subagent or the developer"
    assert session.state().stop_blocks == 0

    ws = session.guard.workspace(session.repo)
    rows = ws.store.db.query("SELECT subject FROM findings WHERE project_id=?", (ws.store.project_id,))
    assert "no-test-run" in {row["subject"] for row in rows}, "still observed for the census"

    held = session.stop()
    assert held["decision"] == "block", "the parent's own budget is intact"
    assert session.state().stop_blocks == 1


def test_a_codex_subagent_sharing_the_session_is_not_gated(session):
    session.prompt()
    session.edit()
    payload = {**_subagent_stop(), "cwd": str(session.repo), "turn_id": "t2"}
    assert codex.handle_payload(session.guard, payload) == {}
    assert session.state().stop_blocks == 0
