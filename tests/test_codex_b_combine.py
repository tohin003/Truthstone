"""COMBINE: one answer for a multi-file Codex patch keeps everything the files said.

``translate.combine()`` used to build a fresh ``Decision`` from a handful of fields, so a
merged patch silently lost whatever it did not name: the sign-off flag (left to the
``render.is_irreversible`` heuristic, which only knows RISK findings), observe mode's
``would_have``, ``unverified_finish``, and every field added to ``Decision`` later
(asks-b's ``signoff_code``). It now starts from the strictest decision and merges only
what it has to; the property test below fails the moment a new field is dropped.
"""

from __future__ import annotations

import enum
import json
import shutil
import subprocess
import types
import typing
from pathlib import Path

import pytest

from agentguard.adapters.codex import render
from agentguard.adapters.codex import translate as codex
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import (
    ChallengeCategory,
    DecisionAction,
    EventType,
    FailureMode,
    Severity,
    Verdict,
)
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision, Finding
from tests.codex_schema import validate

FIXTURES = Path(__file__).parent / "fixtures"

FINDING = Finding(
    category=ChallengeCategory.EVIDENCE,
    verdict=Verdict.CONTRADICTED,
    failure_mode=FailureMode.HALLUCINATED_API,
    severity=Severity.MEDIUM,
    subject="get_active_users",
    summary="`get_active_users` does not exist",
)
# A sign-off the `is_irreversible` heuristic cannot recognise: it is not a RISK finding.
# Today every REQUIRES_HUMAN finding happens to be RISK, which is the only reason a merged
# patch never lost its sign-off in practice; the next kind of sign-off would have.
UNRECOGNISED_SIGNOFF = Finding(
    category=ChallengeCategory.TESTABILITY,
    verdict=Verdict.REQUIRES_HUMAN,
    failure_mode=FailureMode.VERIFICATION_TAMPERING,
    severity=Severity.MEDIUM,
    subject="tests/test_user.py",
    summary="Deleting a test needs the developer's sign-off",
)


def file_event(path: str, tool: str = "Write") -> AgentEvent:
    return AgentEvent(
        event=EventType.PRE_TOOL_USE,
        agent="codex",
        workspace="/workspace",
        session_id="s",
        tool=tool,
        arguments={"file_path": f"/workspace/{path}"},
    )


def bash_event(command: str = "make build") -> AgentEvent:
    return AgentEvent(
        event=EventType.PRE_TOOL_USE,
        agent="codex",
        workspace="/workspace",
        session_id="s",
        tool="Bash",
        arguments={"command": command},
    )


def pre_tool_output(event: AgentEvent, decision: Decision) -> dict:
    out = codex.from_decision(event, decision, "PreToolUse")
    assert validate(out, "pre-tool-use.command.output") == []
    return out


# -- sign-off ------------------------------------------------------------------------


def test_a_signoff_review_in_one_file_renders_the_signoff_deny():
    review = Decision(
        action=DecisionAction.REQUEST_REVIEW,
        reason="Deleting tests/test_user.py removes the only test of this module.",
        findings=[UNRECOGNISED_SIGNOFF],
        signoff_required=True,
    )
    results = [(file_event("src/a.py"), Decision()), (file_event("tests/test_user.py", "Delete"), review)]
    alone = pre_tool_output(results[1][0], review)["hookSpecificOutput"]
    assert alone["permissionDecision"] == "deny"  # the file on its own: the sign-off deny

    event, merged = codex.combine(results)
    assert merged.signoff_required is True
    spec = pre_tool_output(event, merged)["hookSpecificOutput"]
    # Before COMBINE the merged review lost the flag, the heuristic did not recognise the
    # finding, and the patch was only *advised* about — then ran.
    assert spec["permissionDecision"] == "deny"
    lead = alone["permissionDecisionReason"].splitlines()[0]
    assert spec["permissionDecisionReason"].splitlines()[0] == lead
    assert "[tests/test_user.py]" in spec["permissionDecisionReason"]


class _CodedDecision(Decision):
    """A Decision with asks-b's one-shot sign-off code, ahead of the real field."""

    signoff_code: str | None = None


def test_the_signoff_code_travels_with_the_file_that_needs_it():
    results = [
        (file_event("a.py"), _CodedDecision()),
        (file_event("b.py"), _CodedDecision(action=DecisionAction.CHALLENGE, reason="b is wrong")),
        (
            file_event("c.cfg"),
            _CodedDecision(
                action=DecisionAction.REQUEST_REVIEW,
                reason="c needs the developer",
                signoff_required=True,
                signoff_code="K7Q2",
            ),
        ),
    ]
    event, merged = codex.combine(results)
    assert merged.action is DecisionAction.CHALLENGE  # the strictest still wins
    assert event.arg("file_path") == "/workspace/b.py"
    assert merged.signoff_required is True
    assert merged.signoff_code == "K7Q2"


def test_the_signoff_code_rides_along_when_the_strictest_file_carries_it():
    results = [
        (file_event("a.py"), _CodedDecision()),
        (
            file_event("c.cfg"),
            _CodedDecision(
                action=DecisionAction.REQUEST_REVIEW, reason="c", signoff_required=True, signoff_code="Z9"
            ),
        ),
    ]
    assert codex.combine(results)[1].signoff_code == "Z9"


# -- observe mode ----------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=dest, check=True)
    subprocess.run([*git, "add", "-A"], cwd=dest, check=True)
    subprocess.run([*git, "commit", "-qm", "init"], cwd=dest, check=True)
    return dest


HALLUCINATED_PATCH = (
    "*** Begin Patch\n"
    "*** Add File: src/shop/api/report.py\n"
    "+from shop.repositories.user import UserRepository\n"
    "+\n"
    "+\n"
    "+def active_report(session):\n"
    "+    repo = UserRepository(session)\n"
    "+    return repo.get_active_users()\n"
    "*** Update File: src/shop/api/users.py\n"
    "@@\n"
    ' """Users endpoint — SPEC §33\'s "/users endpoint exists"."""\n'
    "+# reviewed\n"
    "*** End Patch"
)


def codex_payload(repo: Path, hook: str, **fields) -> dict:
    return {
        "session_id": "sess-observe",
        "turn_id": "turn-1",
        "transcript_path": None,
        "cwd": str(repo),
        "hook_event_name": hook,
        "model": "gpt-test",
        "permission_mode": "default",
        **fields,
    }


def test_an_observe_mode_patch_keeps_would_have(repo):
    guard = Guard(Settings(observe_only=True))
    try:
        guard.workspace(repo).index.ready(timeout=30)
        prompt = codex_payload(repo, "UserPromptSubmit", prompt="Add an active-users report endpoint")
        assert codex.handle_payload(guard, prompt) == {}
        patch = codex_payload(
            repo,
            "PreToolUse",
            tool_name="apply_patch",
            tool_input={"command": HALLUCINATED_PATCH},
            tool_use_id="call-1",
        )
        events = codex.to_events(patch, root=repo)
        results = [(event, guard.handle(event)) for event in events]
        assert [decision.action for _, decision in results] == [DecisionAction.ALLOW] * 2
        assert {decision.would_have for _, decision in results} == {
            DecisionAction.CHALLENGE,
            DecisionAction.ALLOW,
        }

        event, merged = codex.combine(results)
        assert merged.action is DecisionAction.ALLOW  # observe mode still says nothing
        assert merged.would_have is DecisionAction.CHALLENGE  # ...but knows what it would have
        assert event.arg("file_path").endswith("report.py")
        assert codex.from_decision(event, merged, "PreToolUse") == {}
        assert codex.handle_payload(guard, patch) == {}
    finally:
        guard.close()


def test_the_strictest_would_have_wins_whatever_the_file_order():
    silenced = [
        Decision(would_have=DecisionAction.ALLOW),
        Decision(would_have=DecisionAction.BLOCK),
        Decision(would_have=DecisionAction.REQUEST_REVIEW),
    ]
    for order in (silenced, silenced[::-1]):
        results = [(file_event(f"f{i}.py"), decision) for i, decision in enumerate(order)]
        assert codex.combine(results)[1].would_have is DecisionAction.BLOCK


# -- rewrites ------------------------------------------------------------------------------


def test_one_files_rewrite_is_never_applied_to_another():
    rewrite = Decision(
        action=DecisionAction.MODIFY,
        reason="narrowed",
        additional_context="AgentGuard narrowed this command.",
        updated_arguments={"command": '[ -n "$OUT" ] && rm -rf "$OUT"'},
    )
    results = [(bash_event('rm -rf "$OUT"'), rewrite), (file_event("b.py"), Decision())]
    event, merged = codex.combine(results)
    assert merged.updated_arguments is None
    for rewrites in (False, True):
        out = render.render(event, merged, "PreToolUse", rewrites=rewrites)
        assert validate(out, "pre-tool-use.command.output") == []
        assert "updatedInput" not in json.dumps(out)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_single_action_keeps_its_own_rewrite():
    rewrite = Decision(action=DecisionAction.MODIFY, reason="n", updated_arguments={"command": "safe"})
    pair = (bash_event(), rewrite)
    assert codex.combine([pair]) is pair


def test_combine_does_not_change_the_decisions_it_merges():
    first = Decision(action=DecisionAction.CHALLENGE, reason="a", findings=[FINDING])
    second = Decision(action=DecisionAction.REQUEST_REVIEW, reason="b", signoff_required=True)
    before = (first.model_dump(), second.model_dump())
    codex.combine([(file_event("a.py"), first), (file_event("b.py"), second)])
    assert (first.model_dump(), second.model_dump()) == before


# -- property: no field of the strictest decision is lost -----------------------------------


def sample(annotation: typing.Any) -> typing.Any:
    """A non-default value for a Decision field's type. A field this cannot build fails
    the test loudly: teach it the new type rather than letting the field go unchecked."""
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        return sample(next(arg for arg in args if arg is not type(None)))
    if annotation is bool:
        return True
    if annotation is int:
        return 7
    if annotation is float:
        return 12.5
    if annotation is str:
        return "sample text"
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return list(annotation)[-1]
    if origin is dict:
        return {"command": "echo sample"}
    if origin is list and args == (Finding,):
        return [FINDING]
    raise AssertionError(f"no sample value for {annotation!r}; extend sample() for the new field")


def survives(field: str, strictest: Decision, merged: Decision) -> bool:
    """What "survives" means for each field combine() merges; equality for every other."""
    kept, got = getattr(strictest, field), getattr(merged, field)
    if field in ("reason", "additional_context"):
        return kept.strip() in (got or "")
    if field == "findings":
        return all(finding in got for finding in kept)
    if field in ("level", "latency_ms"):
        return got >= kept
    if field == "updated_arguments":
        return got is None  # a multi-file answer never carries one file's rewrite
    return got == kept


FIELDS = sorted(Decision.model_fields)


@pytest.mark.parametrize("position", ["first", "last"])
@pytest.mark.parametrize("field", FIELDS)
def test_every_field_of_the_strictest_decision_survives_combine(field, position):
    value = sample(Decision.model_fields[field].annotation)
    base = {"action": DecisionAction.CHALLENGE, "reason": "the strict one"}
    if field == "action":
        value = DecisionAction.BLOCK
    strictest = Decision(**{**base, field: value})
    quiet = Decision(level=strictest.level if field == "level" else Decision().level)
    results = [(file_event("strict.py"), strictest), (file_event("quiet.py"), quiet)]
    if position == "last":
        results.reverse()
    event, merged = codex.combine(results)
    assert event.arg("file_path") == "/workspace/strict.py"
    assert survives(field, strictest, merged), (field, getattr(strictest, field), getattr(merged, field))


def test_the_property_test_knows_every_field():
    """``survives`` is an allowlist of merge rules; every other field must be equal. A new
    Decision field is therefore covered the day it lands, through equality."""
    assert {"action", "signoff_required", "would_have", "unverified_finish"} <= set(FIELDS)
