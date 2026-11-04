"""What may reach the agent: the intervention profile (WP7, M7/M9).

Every decision the Guard returns is classified into an **intervention kind**: the reason it
would interrupt, redirect or inform the agent. A **profile** says which kinds may speak, per
phase. ``settings.profile`` names it: ``minimal`` (the default) or ``full``.

Under ``minimal`` exactly these reach the agent — an allowlist, so anything not named here is
withheld, including a kind nobody has heard of:

=====  =================  ==============  ================================================
brief  kind               phase           when
=====  =================  ==============  ================================================
(a)    ``spec_erosion``   Stop            "done" after a normative documented rule was
                                          removed or qualified
(a)    ``test_weakening`` Stop            "done" after tests were weakened, deleted or
                                          skipped (added tests are never flagged)
(a)    ``test_fitting``   Stop            "done" when production code hard-codes
                                          test-specific expectations
(b)    ``failing_tests``  Stop            "done" with relevant tests failing after the last
                                          edit, undisclosed
(e)    ``unread_config``  Stop            "done" when the diff only adds configuration that
                                          nothing outside configuration reads
(c)    ``signoff``        before a tool   an irreversible or destructive action needs the
                                          developer's sign-off (A1: never rationed)
(d)    ``false_premise``  prompt          the prompt asserts a named identifier exists or
                                          already works, and nothing in the repository has it
=====  =================  ==============  ================================================

The planning note (``planning_note``) is off: ``[notes] planning = true`` lets it speak again.

Everything else — routine context, every other challenge, ask, note or Stop reason — is
**recorded, never shown**: :func:`apply` turns the decision into a silent ALLOW that keeps
its findings, says what it would have done (``Decision.would_have``) and carries one more
finding, ``withheld:<kind>``, naming what was held back and quoting it. ``truthstone log``,
the census and ``truthstone replay`` read that.

**How a decision's kind is known.** The sign-off by what it is: a review only the developer
can answer, or the guarded rewrite of a risky command (A1 must hold whatever a check calls
its finding). Anything else by the subject of its primary finding — the first at medium
severity or above — when that subject *is* a kind's name (``spec_erosion``,
``false_premise``…), or by an explicit ``reason_category`` the decision carries. A check
joins a sanctioned kind by naming its finding's subject after it; nothing else is needed.

Stop's own reasons are chosen by the completion arbiter (``verify/arbiter.py``) under the same
setting; this is the choke point every decision passes, Stop included, so no path — old or
new — can reach the agent with a reason outside the list.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from truthstone.core.enums import (
    ChallengeCategory,
    DecisionAction,
    EventType,
    FailureMode,
    Severity,
    Verdict,
)
from truthstone.core.models import Decision, Finding


class Kind(StrEnum):
    """The sanctioned intervention kinds. Stop's five are the arbiter's ``ReasonCategory``
    values, spelled identically."""

    SPEC_EROSION = "spec_erosion"
    TEST_WEAKENING = "test_weakening"
    TEST_FITTING = "test_fitting"
    FAILING_TESTS = "failing_tests"
    UNREAD_CONFIG = "unread_config"
    SIGNOFF = "signoff"
    FALSE_PREMISE = "false_premise"


# Opt-in, and the names of what is only ever recorded: the arbiter's other Stop categories.
PLANNING_NOTE = "planning_note"
UNVERIFIED = "unverified"
UNPARSABLE = "unparsable"
OTHER = "other"
WITHHELD = "withheld:"

MINIMAL = "minimal"
FULL = "full"
PROFILES = (MINIMAL, FULL)

_STOP = frozenset(
    {Kind.SPEC_EROSION, Kind.TEST_WEAKENING, Kind.TEST_FITTING, Kind.FAILING_TESTS, Kind.UNREAD_CONFIG}
)
# The minimal profile: per phase, the only kinds that reach the agent.
MINIMAL_ALLOWED: dict[EventType, frozenset[str]] = {
    EventType.STOP: frozenset(str(k) for k in _STOP),
    EventType.PRE_TOOL_USE: frozenset({str(Kind.SIGNOFF)}),
    EventType.USER_PROMPT: frozenset({str(Kind.FALSE_PREMISE)}),
}
_NAMED = frozenset(str(k) for k in Kind) | {PLANNING_NOTE, UNVERIFIED, UNPARSABLE}
_SPEAKING = (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    allowed: dict[EventType, frozenset[str]]
    allow_all: bool = False

    def allows(self, phase: EventType, kind: str) -> bool:
        return self.allow_all or kind in self.allowed.get(phase, frozenset())


def build(name: str = MINIMAL, planning: bool = False) -> Profile:
    """The named profile; an unknown name is the minimal one (the quiet direction)."""
    if name == FULL:
        return Profile(FULL, dict(MINIMAL_ALLOWED), allow_all=True)
    allowed = dict(MINIMAL_ALLOWED)
    if planning:
        allowed[EventType.USER_PROMPT] = allowed[EventType.USER_PROMPT] | {PLANNING_NOTE}
    return Profile(MINIMAL, allowed)


_CACHE: dict[tuple[str, bool], Profile] = {}


def active(settings: Any) -> Profile:
    """The profile ``settings`` select: ``settings.profile`` and ``[notes] planning``."""
    name = str(getattr(settings, "profile", MINIMAL) or MINIMAL)
    notes = getattr(settings, "notes", None)
    planning = bool(getattr(notes, "planning", False))
    key = (name, planning)
    if key not in _CACHE:
        _CACHE[key] = build(name, planning)
    return _CACHE[key]


# -- classification ------------------------------------------------------------------------


def is_signoff(decision: Decision) -> bool:
    """A decision only the developer can answer (A1): never withheld, never rationed."""
    if decision.signoff_required:
        return True
    if decision.action is DecisionAction.REQUEST_REVIEW:
        return any(
            f.category is ChallengeCategory.RISK
            and (f.verdict is Verdict.REQUIRES_HUMAN or f.severity in (Severity.HIGH, Severity.CRITICAL))
            for f in decision.findings
        )
    return decision.action is DecisionAction.MODIFY


def primary(decision: Decision) -> Finding | None:
    """The finding a decision speaks about: its first at medium severity or above, else its
    first. Producers put the reason first."""
    for finding in decision.findings:
        if finding.severity in _SPEAKING and not finding.subject.startswith(WITHHELD):
            return finding
    return next((f for f in decision.findings if not f.subject.startswith(WITHHELD)), None)


def kind_of(decision: Decision) -> str:
    """The intervention kind of a decision: a sanctioned kind's name, or ``other:<what>``."""
    if is_signoff(decision):
        return str(Kind.SIGNOFF)
    explicit = getattr(decision, "reason_category", None)
    if explicit:
        return str(explicit)
    finding = primary(decision)
    if finding is not None:
        if finding.subject in _NAMED:
            return finding.subject
        return f"{OTHER}:{(finding.subject or str(finding.category))[:60]}"
    if decision.additional_context:
        return f"{OTHER}:context"
    return f"{OTHER}:{decision.action}"


def says_anything(decision: Decision) -> bool:
    """Whether the decision could reach anyone: an action, context, or a developer notice."""
    return (
        decision.action is not DecisionAction.ALLOW
        or bool(decision.additional_context)
        or bool(decision.unverified_finish)
    )


# -- the choke point -----------------------------------------------------------------------


def apply(phase: EventType, decision: Decision, profile: Profile) -> Decision:
    """``decision`` as the profile lets it reach the agent: unchanged when its kind may speak
    in this phase, otherwise withheld — a silent ALLOW that keeps everything for the record."""
    if not says_anything(decision) or profile.allow_all:
        return decision
    kind = kind_of(decision)
    if profile.allows(phase, kind):
        return decision
    return withhold(decision, kind)


def withhold(decision: Decision, kind: str) -> Decision:
    said = (decision.reason or decision.additional_context or decision.unverified_finish or "").strip()
    marker = Finding(
        category=ChallengeCategory.EVIDENCE,
        verdict=Verdict.SUPPORTED,
        # What Truthstone held back is not a failure of the agent's; the census skips it.
        failure_mode=FailureMode.NOT_A_FAILURE,
        severity=Severity.INFO,
        subject=f"{WITHHELD}{kind}",
        summary=f"recorded, not shown ({decision.action})",
        detail=said[:600],
    )
    would_have = decision.would_have or (
        decision.action if decision.action is not DecisionAction.ALLOW else None
    )
    return Decision(
        action=DecisionAction.ALLOW,
        findings=[*decision.findings, marker],
        level=decision.level,
        latency_ms=decision.latency_ms,
        decision_id=decision.decision_id,
        would_have=would_have,
    )


def withheld_kind(decision: Decision) -> str | None:
    """The kind :func:`withhold` recorded on a decision, if any."""
    for finding in decision.findings:
        if finding.subject.startswith(WITHHELD):
            return finding.subject[len(WITHHELD) :]
    return None
