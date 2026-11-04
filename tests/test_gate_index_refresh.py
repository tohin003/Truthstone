"""R4: the index is refreshed at session and prompt boundaries.

D6 E4: a long-lived Guard went on vouching for a method that had been reverted
underneath it between sessions, while a fresh Guard challenged the same Write. The only
refreshes were at Stop and after shell commands. SessionStart and UserPromptSubmit now
refresh too, rate-limited to one scan per `BOUNDARY_REFRESH_INTERVAL` seconds.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from truthstone.core import engine
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction, EventType
from truthstone.core.events import AgentEvent

FIXTURES = Path(__file__).parent / "fixtures"
REPOSITORY = "src/shop/repositories/user.py"
REPORT = textwrap.dedent(
    """
    from shop.repositories.user import UserRepository

    def report(session):
        return UserRepository(session).get_active_users()
    """
)
METHOD = "\n    def get_active_users(self):\n        return []\n"


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


def _event(repo: Path, kind: EventType, session: str, **fields) -> AgentEvent:
    return AgentEvent(event=kind, agent="claude-code", workspace=str(repo), session_id=session, **fields)


def _write_report(guard: Guard, repo: Path, session: str):
    args = {"file_path": "src/shop/api/report.py", "content": REPORT}
    return guard.handle(_event(repo, EventType.PRE_TOOL_USE, session, tool="Write", arguments=args))


def _add_method_in_session_one(guard: Guard, repo: Path) -> str:
    original = (repo / REPOSITORY).read_text()
    guard.handle(_event(repo, EventType.USER_PROMPT, "s1", prompt_text="Add get_active_users."))
    (repo / REPOSITORY).write_text(original + METHOD)
    edit = {"file_path": REPOSITORY}
    guard.handle(_event(repo, EventType.POST_TOOL_USE, "s1", tool="Edit", arguments=edit))
    assert guard.workspace(repo).index.find_symbol("get_active_users")
    guard.handle(_event(repo, EventType.SESSION_END, "s1"))
    return original


def test_index_sees_external_changes_between_sessions(repo):
    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        ws.index.ready(timeout=30)
        original = _add_method_in_session_one(guard, repo)

        (repo / REPOSITORY).write_text(original)  # the developer reverts it; no hook fires
        ws.index.last_refresh -= engine.BOUNDARY_REFRESH_INTERVAL + 1  # time passes

        guard.handle(_event(repo, EventType.SESSION_START, "s2"))
        guard.handle(_event(repo, EventType.USER_PROMPT, "s2", prompt_text="Add an active-users report."))
        decision = _write_report(guard, repo, "s2")
    finally:
        guard.close()
    assert decision.action is DecisionAction.CHALLENGE
    assert "get_active_users" in decision.reason


def test_a_prompt_boundary_refreshes_too(repo):
    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        ws.index.ready(timeout=30)
        original = _add_method_in_session_one(guard, repo)
        (repo / REPOSITORY).write_text(original)
        ws.index.last_refresh -= engine.BOUNDARY_REFRESH_INTERVAL + 1

        guard.handle(_event(repo, EventType.USER_PROMPT, "s2", prompt_text="Add an active-users report."))
        assert not ws.index.find_symbol("get_active_users")
    finally:
        guard.close()


def test_boundary_refreshes_are_rate_limited(repo):
    """A boundary within the interval of the last scan does not re-scan the tree."""
    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        ws.index.ready(timeout=30)
        original = _add_method_in_session_one(guard, repo)
        (repo / REPOSITORY).write_text(original)
        ws.index.refresh(min_interval=0)  # a scan just happened (it sees the revert)...
        (repo / REPOSITORY).write_text(original + METHOD)  # ...then the method is back

        guard.handle(_event(repo, EventType.USER_PROMPT, "s2", prompt_text="Next task."))
        assert not ws.index.find_symbol("get_active_users"), "no re-scan within the interval"
    finally:
        guard.close()
