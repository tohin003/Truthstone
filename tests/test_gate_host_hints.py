"""H5 (core): host hints — what a host knows that its payload does not say.

Upstreamed from Pebble's vendored seams: an embedding host's own read-only tools
(searches, git reads, test runs on a snapshot) keep their names in the record but never
enter validation (`raw["host_read_only"]` in Pebble's copy), and the host decides the
test waiver when it can (`TaskSpec.tests_waiver`). In the core they are one canonical
field, `AgentEvent.host_hints`.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction, EventType
from truthstone.core.events import AgentEvent

FIXTURES = Path(__file__).parent / "fixtures"
COVERED = "src/shop/utils/pagination.py"
HALLUCINATION = textwrap.dedent(
    """
    from shop.repositories.user import UserRepository

    def report(session):
        return UserRepository(session).get_active_users()
    """
)


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


def _event(repo: Path, kind: EventType, hints: dict | None = None, **fields) -> AgentEvent:
    return AgentEvent(
        event=kind, agent="pebble", workspace=str(repo), session_id="s1", host_hints=hints or {}, **fields
    )


class TestReadOnly:
    def test_the_hint_makes_any_tool_read_only(self):
        event = AgentEvent(event=EventType.PRE_TOOL_USE, tool="SearchFiles", host_hints={"read_only": True})
        assert event.is_read_only and not event.is_mutating
        assert not AgentEvent(event=EventType.PRE_TOOL_USE, tool="SearchFiles").is_read_only

    def test_a_false_hint_never_removes_read_only_ness(self):
        event = AgentEvent(event=EventType.PRE_TOOL_USE, tool="Read", host_hints={"read_only": False})
        assert event.is_read_only

    def test_a_read_only_host_tool_is_not_validated(self, guard, repo):
        guard.handle(_event(repo, EventType.USER_PROMPT, prompt_text="Add an active-users report."))
        args = {"file_path": "src/shop/api/report.py", "content": HALLUCINATION}
        plain = guard.handle(_event(repo, EventType.PRE_TOOL_USE, tool="Write", arguments=args))
        hinted = guard.handle(
            _event(repo, EventType.PRE_TOOL_USE, {"read_only": True}, tool="Write", arguments=args)
        )
        assert plain.action is DecisionAction.CHALLENGE
        assert hinted.action is DecisionAction.ALLOW and hinted.is_silent

    def test_a_read_only_host_tool_touches_nothing(self, guard, repo):
        guard.handle(_event(repo, EventType.USER_PROMPT, prompt_text="Fix the paginate helper."))
        hinted, args = {"read_only": True}, {"file_path": COVERED}
        guard.handle(_event(repo, EventType.POST_TOOL_USE, hinted, tool="Write", arguments=args))
        assert guard.workspace(repo).task_state(None, "s1").touched_files == set()


class TestTestsWaived:
    def test_the_host_can_waive_tests_the_prompt_does_not_mention(self, guard, repo):
        hinted = {"tests_waived": True}
        guard.handle(_event(repo, EventType.USER_PROMPT, hinted, prompt_text="Fix the paginate helper."))
        assert guard.workspace(repo).task_state(None, "s1").spec.tests_waived
        guard.handle(_event(repo, EventType.POST_TOOL_USE, tool="Edit", arguments={"file_path": COVERED}))
        assert guard.handle(_event(repo, EventType.STOP)).action is DecisionAction.ALLOW

    def test_the_host_can_overrule_a_waiver_in_the_prompt(self, guard, repo):
        guard.handle(
            _event(
                repo,
                EventType.USER_PROMPT,
                {"tests_waived": False},
                prompt_text="Fix the paginate helper. Do not run tests.",
            )
        )
        assert not guard.workspace(repo).task_state(None, "s1").spec.tests_waived
        guard.handle(_event(repo, EventType.POST_TOOL_USE, tool="Edit", arguments={"file_path": COVERED}))
        assert guard.handle(_event(repo, EventType.STOP)).action is DecisionAction.BLOCK

    def test_a_non_boolean_hint_is_ignored(self, guard, repo):
        hinted = {"tests_waived": "yes"}
        guard.handle(_event(repo, EventType.USER_PROMPT, hinted, prompt_text="Fix the paginate helper."))
        spec = guard.workspace(repo).task_state(None, "s1").spec
        assert spec.tests_waiver is None and not spec.tests_waived
