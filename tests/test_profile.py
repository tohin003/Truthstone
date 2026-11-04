"""The minimal-intervention profile (WP7, M7/M9): only the sanctioned kinds reach the agent.

Under ``settings.profile = "minimal"`` (the default), a decision speaks only when its kind is
allowed in its phase: at Stop the five yardstick and completion kinds, before a tool the
developer's sign-off, at the prompt the false-premise note. Everything else is recorded, never
shown: a silent ALLOW that keeps the findings, the would-have action and a ``withheld:<kind>``
marker quoting what was held back. Synthetic decisions and repositories only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from truthstone.adapters.codex import translate
from truthstone.core import profile
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import (
    ChallengeCategory,
    DecisionAction,
    EventType,
    FailureMode,
    Severity,
    Verdict,
)
from truthstone.core.models import Decision, Finding

MINIMAL = profile.build("minimal")
FULL = profile.build("full")


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about the product's default: no harness override."""
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


def _finding(subject: str, severity: Severity = Severity.MEDIUM, **kw) -> Finding:
    return Finding(
        category=kw.pop("category", ChallengeCategory.SCOPE),
        verdict=kw.pop("verdict", Verdict.INSUFFICIENT_EVIDENCE),
        failure_mode=kw.pop("failure_mode", FailureMode.UNRELATED_FILES_MODIFIED),
        severity=severity,
        subject=subject,
        summary=f"about {subject}",
    )


def _challenge(subject: str, action: DecisionAction = DecisionAction.CHALLENGE) -> Decision:
    return Decision(action=action, reason=f"Truthstone objects: {subject}", findings=[_finding(subject)])


# -- the setting -----------------------------------------------------------------------------


def test_minimal_is_the_default_and_full_is_opt_in(isolated_home: Path):
    assert Settings().profile == "minimal"
    assert profile.active(Settings()).name == "minimal"
    assert profile.active(Settings(profile="full")).allow_all
    (isolated_home / "config.toml").write_text('profile = "full"\n')
    assert Settings.load().profile == "full"


def test_the_environment_pins_a_profile_over_the_config(isolated_home: Path, monkeypatch):
    (isolated_home / "config.toml").write_text('profile = "full"\n')
    monkeypatch.setenv("TRUTHSTONE_PROFILE", "minimal")
    assert Settings.load().profile == "minimal"
    monkeypatch.setenv("TRUTHSTONE_PROFILE", "loud")  # not a profile: ignored
    assert Settings.load().profile == "full"


def test_an_unknown_profile_name_is_the_quiet_one():
    assert profile.build("chatty").name == "minimal"


# -- the allowlist ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind", ["spec_erosion", "test_weakening", "test_fitting", "failing_tests", "unread_config"]
)
def test_a_sanctioned_stop_reason_speaks(kind):
    decision = _challenge(kind, DecisionAction.BLOCK)
    assert profile.apply(EventType.STOP, decision, MINIMAL) is decision


@pytest.mark.parametrize(
    "subject", ["stale-verification", "no-test-run", "unverified", "unparsable", "a-check-nobody-registered"]
)
def test_any_other_stop_reason_is_recorded_not_shown(subject):
    decision = _challenge(subject, DecisionAction.BLOCK)
    out = profile.apply(EventType.STOP, decision, MINIMAL)
    assert out.action is DecisionAction.ALLOW and not out.reason and not out.additional_context
    assert out.would_have is DecisionAction.BLOCK
    assert profile.withheld_kind(out) == (
        subject if subject in ("unverified", "unparsable") else f"other:{subject}"
    )
    marker = out.findings[-1]
    assert marker.failure_mode is FailureMode.NOT_A_FAILURE and "Truthstone objects" in marker.detail
    assert out.findings[0] == decision.findings[0]  # the record is kept


def test_a_stop_reason_is_allowed_only_at_stop():
    """A kind belongs to its phase: a failing-tests "reason" before a tool is not (b)."""
    decision = _challenge("failing_tests")
    assert profile.apply(EventType.PRE_TOOL_USE, decision, MINIMAL).action is DecisionAction.ALLOW


def test_the_developer_sign_off_always_reaches_them():
    review = Decision(
        action=DecisionAction.REQUEST_REVIEW,
        reason="needs sign-off",
        signoff_required=True,
        findings=[
            _finding(
                "git reset --hard",
                Severity.HIGH,
                category=ChallengeCategory.RISK,
                verdict=Verdict.REQUIRES_HUMAN,
                failure_mode=FailureMode.DESTRUCTIVE_ACTION,
            )
        ],
    )
    assert profile.apply(EventType.PRE_TOOL_USE, review, MINIMAL) is review
    # The flag lost on the way: still a sign-off by what it is.
    unflagged = review.model_copy(update={"signoff_required": False})
    assert profile.apply(EventType.PRE_TOOL_USE, unflagged, MINIMAL) is unflagged
    # A guarded rewrite of a risky command is the sign-off's other form.
    modify = Decision(
        action=DecisionAction.MODIFY, reason="narrowed", findings=[_finding("modified command")]
    )
    assert profile.apply(EventType.PRE_TOOL_USE, modify, MINIMAL) is modify


@pytest.mark.parametrize("subject", ["scope", "proportionality", "SomeClass.missing", "requests"])
def test_every_other_pre_tool_challenge_is_recorded_not_shown(subject):
    out = profile.apply(EventType.PRE_TOOL_USE, _challenge(subject), MINIMAL)
    assert out.action is DecisionAction.ALLOW and out.would_have is DecisionAction.CHALLENGE
    assert profile.withheld_kind(out) == f"other:{subject}"


def test_an_advisory_review_is_not_a_sign_off():
    advisory = Decision(
        action=DecisionAction.REQUEST_REVIEW, reason="look", findings=[_finding("force push-ish")]
    )
    assert profile.apply(EventType.PRE_TOOL_USE, advisory, MINIMAL).action is DecisionAction.ALLOW


def test_the_premise_note_speaks_at_the_prompt_and_nowhere_else():
    note = Decision(additional_context="`X_Y` appears nowhere", findings=[_finding("false_premise")])
    assert profile.apply(EventType.USER_PROMPT, note, MINIMAL) is note
    later = profile.apply(EventType.POST_TOOL_USE, note, MINIMAL)
    assert later.additional_context is None and profile.withheld_kind(later) == "false_premise"


def test_routine_context_is_recorded_not_shown():
    for phase in (EventType.SESSION_START, EventType.USER_PROMPT, EventType.POST_TOOL_USE):
        out = profile.apply(phase, Decision(additional_context="fyi: something"), MINIMAL)
        assert out.additional_context is None and profile.withheld_kind(out) == "other:context"
        assert out.would_have is None  # nothing would have been held: only said


def test_the_planning_note_is_off_unless_turned_on():
    note = Decision(
        additional_context="[Truthstone] plan", findings=[_finding("planning_note", Severity.INFO)]
    )
    assert profile.apply(EventType.USER_PROMPT, note, MINIMAL).additional_context is None
    assert profile.apply(EventType.USER_PROMPT, note, profile.build("minimal", planning=True)) is note


def test_a_developer_notice_about_an_unsanctioned_stop_is_withheld_too():
    gave_up = Decision(unverified_finish="stale run", findings=[_finding("stale-verification")])
    assert profile.apply(EventType.STOP, gave_up, MINIMAL).unverified_finish is None


def test_the_full_profile_lets_everything_through():
    for decision in (_challenge("scope"), Decision(additional_context="fyi")):
        assert profile.apply(EventType.PRE_TOOL_USE, decision, FULL) is decision


def test_a_silent_decision_is_left_alone():
    quiet = Decision.allow()
    assert profile.apply(EventType.PRE_TOOL_USE, quiet, MINIMAL) is quiet


# -- through the engine and the Codex adapter ----------------------------------------------------


def _python_repo(root: Path) -> Path:
    repo = root / "proj"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "__init__.py").write_text("")
    (repo / "pkg" / "core.py").write_text("def real_helper():\n    return 1\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_core.py").write_text(
        "from pkg.core import real_helper\n\n\ndef test_it():\n    assert real_helper() == 1\n"
    )
    return repo


def _payload(repo: Path, name: str, **fields) -> dict:
    return {"session_id": "s", "turn_id": "t", "cwd": str(repo), "hook_event_name": name, **fields}


def _edit_importing_a_missing_name(repo: Path) -> dict:
    patch = (
        "*** Begin Patch\n"
        f"*** Add File: {repo / 'pkg' / 'use.py'}\n"
        "+from pkg.core import imaginary_helper\n"
        "+\n"
        "+VALUE = imaginary_helper()\n"
        "*** End Patch\n"
    )
    return _payload(repo, "PreToolUse", tool_name="apply_patch", tool_input={"command": patch})


@pytest.mark.parametrize("name", ["minimal", "full"])
def test_an_evidence_challenge_reaches_the_agent_only_under_full(tmp_path, name):
    repo = _python_repo(tmp_path)
    guard = Guard(Settings(profile=name))
    try:
        guard.workspace(repo).index.ready(timeout=30)
        translate.dispatch(guard, _payload(repo, "UserPromptSubmit", prompt="Add a VALUE module to pkg."))
        output, _results, decision = translate.dispatch(guard, _edit_importing_a_missing_name(repo))
    finally:
        guard.close()
    if name == "full":
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    else:
        assert output == {}
        assert decision.would_have is DecisionAction.CHALLENGE
        assert (profile.withheld_kind(decision) or "").startswith("other:")


def test_routine_prompt_injects_nothing(tmp_path):
    repo = _python_repo(tmp_path)
    prompt = "real_helper() in pkg/core.py should return 2. Please fix it and run the tests."
    for settings, expect_context in (
        (Settings(), False),
        (Settings(profile="full"), True),
        (Settings(notes={"planning": True}), True),
    ):
        guard = Guard(settings)
        try:
            guard.workspace(repo).index.ready(timeout=30)
            output, _results, decision = translate.dispatch(
                guard, _payload(repo, "UserPromptSubmit", prompt=prompt)
            )
        finally:
            guard.close()
        assert bool(output.get("hookSpecificOutput", {}).get("additionalContext")) is expect_context, settings
        if not expect_context:
            assert output == {} and decision.additional_context is None
