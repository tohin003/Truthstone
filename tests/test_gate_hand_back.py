"""G4a: the Completion Gate never blocks an honest hand-back.

Probe E: after a visibly failing run the agent wrote "I could not make test_get_by_id
pass… Should I mock it or leave it?" and was blocked with "verification_failed" — a
turn that claimed nothing. Each scenario runs through Claude-Code-shaped payloads, the
real adapter and the real Guard.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.test_gate_timeline import FAIL, SOURCE, Session
from truthstone.adapters.codex import translate as codex
from truthstone.core.config import Settings
from truthstone.core.engine import Guard

FIXTURES = Path(__file__).parent / "fixtures"
PROBE_E = "I could not make test_get_by_id pass\N{HORIZONTAL ELLIPSIS} Should I mock it or leave it?"


@pytest.fixture
def session(tmp_path):
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    s = Session(repo)
    yield s
    s.close()


def _findings(session: Session) -> dict[str, str]:
    ws = session.guard.workspace(session.repo)
    rows = ws.store.db.query(
        "SELECT subject, failure_mode FROM findings WHERE project_id=?", (ws.store.project_id,)
    )
    return {row["subject"]: row["failure_mode"] for row in rows}


def test_question_not_blocked(session):
    """Edited covered code, ran nothing, and asked: not a completion claim."""
    session.prompt()
    session.edit()
    assert session.stop("Should page 0 raise a ValueError, or be treated as page 1?") == {}
    assert _findings(session)["honest-hand-back"] == "unverified_change"


def test_disclosure_not_blocked(session):
    """Probe E."""
    session.prompt()
    session.edit()
    session.run("pytest -q 2>&1 | tail -15", FAIL)
    out = session.stop(PROBE_E)
    assert out == {}, "nothing reaches Claude, and no 'gave up' systemMessage either"
    assert "honest-hand-back" in _findings(session)
    assert "failing-tests-on-completion" not in _findings(session)


def test_claim_plus_question_still_blocked(session):
    session.prompt()
    session.edit()
    session.run("pytest -q 2>&1 | tail -15", FAIL)
    held = session.stop("Done - all tests pass. Want me to update the README too?")
    assert held["decision"] == "block"
    assert "verification_failed" in held["reason"]


def test_a_bare_done_is_still_blocked(session):
    session.prompt()
    session.edit()
    held = session.stop("Done.")
    assert held["decision"] == "block"


def test_tdd_red_phase_not_blocked(session):
    """The developer asked for a failing test; the only failure is in the test this task
    wrote."""
    session.prompt("Write a failing test that reproduces the paginate page-0 bug. Don't fix it yet.")
    session.edit("tests/test_page_zero.py", append="def test_zero():\n    assert False\n")
    failing = "F\nFAILED tests/test_page_zero.py::test_zero - assert False\n1 failed in 0.01s\n"
    session.run("pytest tests/test_page_zero.py", failing, exit_code=1)
    assert session.stop("Added tests/test_page_zero.py; it fails as expected.") == {}
    assert _findings(session)["tdd-red-phase"] == "not_a_failure"


def test_red_phase_needs_the_requests_cue(session):
    session.prompt("Add a test for page 0.")
    session.edit("tests/test_page_zero.py", append="def test_zero():\n    assert False\n")
    failing = "F\nFAILED tests/test_page_zero.py::test_zero - assert False\n1 failed in 0.01s\n"
    session.run("pytest tests/test_page_zero.py", failing, exit_code=1)
    held = session.stop("Added the test.")
    assert held["decision"] == "block"


def test_red_phase_does_not_cover_an_existing_failing_test(session):
    session.prompt("Write a failing test that reproduces the paginate bug.")
    session.edit("tests/test_page_zero.py", append="def test_zero():\n    assert False\n")
    session.edit(SOURCE)
    failing = (
        "FF\nFAILED tests/test_page_zero.py::test_zero - assert False\n"
        "FAILED tests/test_pagination.py::test_paginate - boom\n2 failed in 0.01s\n"
    )
    session.run("pytest", failing, exit_code=1)
    held = session.stop("The new test fails as expected.")
    assert held["decision"] == "block"


def test_the_live_codex_stop_message_is_an_honest_hand_back(tmp_path):
    """Captured from a live `codex exec`: "...The combined patch couldn't be completed
    because..." A disclosure, so an unverified edit is not held."""
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    guard = Guard(Settings(profile="full"))
    try:
        guard.workspace(repo).index.ready(timeout=30)
        base = {"session_id": "sess-codex", "cwd": str(repo), "turn_id": "t1"}
        prompt = json.loads((FIXTURES / "codex_payloads" / "UserPromptSubmit.json").read_text())
        codex.handle_payload(guard, {**prompt, **base, "prompt": "Fix the paginate helper."})
        text = (
            "*** Begin Patch\n*** Update File: src/shop/utils/pagination.py\n@@\n"
            "-def paginate(query, page: int = 1, per_page: int = 20):\n"
            "+def paginate(query, page: int = 1, per_page: int = 25):\n*** End Patch"
        )
        patch = {
            **base,
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": text},
            "tool_response": "Success.",
        }
        codex.handle_payload(guard, patch)
        stop = json.loads((FIXTURES / "codex_payloads" / "Stop.json").read_text())
        out = codex.handle_payload(guard, {**stop, **base})
    finally:
        guard.close()
    assert out == {}
