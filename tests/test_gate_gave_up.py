"""G10 (core): an explicit "the gate gave up" flag.

When the gate's per-task budget is spent, or a stop hook is already holding the turn, the
core lets the turn end — correctly, a gate that never lets go is a loop — but it did so
silently, and the Claude adapter had to infer a give-up from findings (which an honest
hand-back also carries). The core now says so on `Decision.unverified_finish`, and the
Claude adapter turns it into a `systemMessage` for the developer.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.conftest import stop_event
from tests.test_gate_timeline import FAIL, Session
from truthstone.adapters.claude_code import translate as claude
from truthstone.core.config import Settings
from truthstone.core.engine import Guard

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


def test_budget_spent_sets_the_flag_and_tells_the_developer(repo):
    session = Session(repo)
    try:
        session.prompt()
        session.edit()
        session.run("pytest -q", FAIL, exit_code=1)
        first, second = session.stop("Done."), session.stop("Done.")
        assert first["decision"] == "block" and second["decision"] == "block"

        event = claude.to_event({**stop_event("Done."), "cwd": str(repo)})
        decision = session.guard.handle(event)
        out = claude.from_decision(event, decision, "Stop")
    finally:
        session.close()
    assert decision.unverified_finish and "pytest -q" in decision.unverified_finish
    assert set(out) == {"systemMessage"}
    assert "ended unverified" in out["systemMessage"]
    assert "pytest -q" in out["systemMessage"]


def test_a_stop_hook_already_holding_the_turn_sets_the_flag(repo):
    session = Session(repo)
    try:
        session.prompt()
        session.edit()
        assert session.stop("Done.")["decision"] == "block"
        out = session.send(stop_event("Done.", stop_hook_active=True))
    finally:
        session.close()
    assert "systemMessage" in out and "no tests were run" in out["systemMessage"]


def test_observe_mode_never_sets_the_flag(repo):
    settings = Settings(profile="full")
    settings.observe_only = True
    guard = Guard(settings)
    try:
        guard.workspace(repo).index.ready(timeout=30)
        session = Session.__new__(Session)
        session.repo, session.guard = repo, guard
        session.prompt()
        session.edit()
        decisions = []
        for _ in range(3):
            event = claude.to_event({**stop_event("Done."), "cwd": str(repo)})
            decisions.append(guard.handle(event))
    finally:
        guard.close()
    assert all(d.unverified_finish is None for d in decisions)
    assert all(d.would_have is not None for d in decisions), "observe mode saw the problem"


def test_a_passing_or_exempted_turn_never_sets_it(repo):
    session = Session(repo)
    try:
        session.prompt()
        session.edit()
        session.run("pytest -q", FAIL, exit_code=1)
        event = claude.to_event(
            {**stop_event("I could not make it pass. Should I mock the DB?"), "cwd": str(repo)}
        )
        decision = session.guard.handle(event)
    finally:
        session.close()
    assert decision.unverified_finish is None
    assert claude.from_decision(event, decision, "Stop") == {}
