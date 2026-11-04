"""What may reach the agent: intervention kinds and the profile that allows them (WP7, M7/M9).

Every decision the Guard returns is classified here into one **intervention kind**: the
reason it would interrupt, redirect or inform the agent. A **profile** is an allowlist of
kinds. Under the ``minimal`` profile (the default), only the sanctioned situations speak:

=====  ======================  ========================================================
brief  kind                    when
=====  ======================  ========================================================
(a)    ``spec_integrity``      "done" after a normative documented rule was removed or
                               qualified
(a)    ``test_integrity``      "done" after tests were weakened, deleted or skipped
                               (added tests are never flagged)
(a)    ``test_specific_code``  "done" when production code hard-codes test-specific
                               expectations
(b)    ``failing_tests``       "done" with relevant tests failing after the last edit,
                               undisclosed
(c)    ``signoff``             an irreversible or destructive action needs the
                               developer's sign-off (A1; never rationed)
(d)    ``false_premise``       the prompt asserts that a named identifier exists or
                               already works, and nothing in the repository has it
(e)    ``unread_config``       "done" when the diff only adds configuration nothing
                               outside configuration reads, for a behavioural claim
=====  ======================  ========================================================

Everything else — the planning note, routine context, every other challenge, ask or
Stop reason — is **recorded, never shown**: the decision keeps its findings and says what
it would have done (``Decision.would_have``), and the kind it would have spoken under.

A kind is named by the subject of the finding behind the decision (``SUBJECT_KINDS``): a
new check joins a sanctioned kind by using, or registering, its subject there — one line.
A decision with no sanctioned finding is ``other:<subject>``, so a summary still says what
it was. The one exception is the sign-off, which is recognised by what it is (a review the
developer must answer, or a guarded rewrite of a risky command) rather than by subject:
A1 must hold whatever a check calls its finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from truthstone.core.enums import ChallengeCategory, DecisionAction, Severity, Verdict
from truthstone.core.models import Decision, Finding


class Kind(StrEnum):
    """The sanctioned intervention kinds (the minimal profile's allowlist)."""

    SPEC_INTEGRITY = "spec_integrity"
    TEST_INTEGRITY = "test_integrity"
    TEST_SPECIFIC_CODE = "test_specific_code"
    FAILING_TESTS = "failing_tests"
    SIGNOFF = "signoff"
    FALSE_PREMISE = "false_premise"
    UNREAD_CONFIG = "unread_config"


# Opt-in kinds: recorded under the minimal profile unless configuration turns them on.
PLANNING_NOTE = "planning_note"
OTHER = "other"

# Finding subject -> the sanctioned kind it speaks under. A check that should be able to
# reach the agent names its finding with one of these subjects, or adds its own here.
SUBJECT_KINDS: dict[str, str] = {
    # (a) the yardstick, at Stop
    "spec-integrity": Kind.SPEC_INTEGRITY,
    "test-integrity": Kind.TEST_INTEGRITY,
    "test-specific-code": Kind.TEST_SPECIFIC_CODE,
    # (b) failing tests at "done" (the completion gate, then the arbiter)
    "failing-tests-on-completion": Kind.FAILING_TESTS,
    "failing-relevant-tests": Kind.FAILING_TESTS,
    # (c) a risky command Truthstone narrowed: the guarded form of a sign-off
    "modified command": Kind.SIGNOFF,
    # (d) the prompt's premise
    "false-premise": Kind.FALSE_PREMISE,
    # (e) configuration nothing reads
    "unread-config": Kind.UNREAD_CONFIG,
    # opt-in
    "planning-note": PLANNING_NOTE,
}

# Severities at which a finding is what a decision speaks about (below: observations).
_SPEAKING = (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)

MINIMAL = "minimal"
FULL = "full"
PROFILES = (MINIMAL, FULL)


@dataclass(frozen=True, slots=True)
class Profile:
    """An allowlist of intervention kinds. ``FULL`` allows everything (the pre-v0.2
    behaviour, for comparison and for developers who want every challenge)."""

    name: str
    allowed: frozenset[str]
    allow_all: bool = False

    def allows(self, kind: str) -> bool:
        return self.allow_all or kind in self.allowed


def build(name: str = MINIMAL, extra: tuple[str, ...] | list[str] = ()) -> Profile:
    """The named profile, plus any opt-in kinds (``[interventions] allow``, or the planning
    note when ``[notes] planning`` is on). An unknown name is the minimal profile: the
    quiet direction."""
    if name == FULL:
        return Profile(FULL, frozenset(Kind) | frozenset(extra), allow_all=True)
    return Profile(MINIMAL, frozenset(str(kind) for kind in Kind) | frozenset(extra))


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
    """The finding a decision speaks about: its first at medium severity or above, else
    its first. Producers put the reason first (the completion gate does)."""
    for finding in decision.findings:
        if finding.severity in _SPEAKING:
            return finding
    return decision.findings[0] if decision.findings else None


def kind_of_finding(finding: Finding) -> str:
    kind = SUBJECT_KINDS.get(finding.subject)
    if kind is not None:
        return str(kind)
    label = finding.subject or str(finding.category)
    # Subjects can carry a path or a symbol; keep the summary readable and bounded.
    return f"{OTHER}:{label[:60]}"


def kind_of(decision: Decision) -> str:
    """The intervention kind of a decision: what it says, or would say, to the agent."""
    if is_signoff(decision):
        return str(Kind.SIGNOFF)
    finding = primary(decision)
    if finding is not None:
        return kind_of_finding(finding)
    if decision.additional_context:
        return f"{OTHER}:context"
    return f"{OTHER}:{decision.action}"
