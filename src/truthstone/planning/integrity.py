"""The integrity note: what a "done" may not be built on, said once per session (day 3).

Agents asked to make something pass will sometimes make the yardstick pass instead: an existing
test edited, skipped or narrowed, a value the tests use special-cased, a documented rule rewritten
the request never mentioned. The completion arbiter catches some of these at Stop, from the
evidence; this note says the rule up front, and names the honest way out, so the agent need not
find one. Published measurements on agent test-gaming point the same way: naming the forbidden
shortcuts and offering an explicit, acceptable "cannot be done" exit lowers gaming far more than
a generic "do not cheat".

It is context, never a hold or a block, and it is off unless ``[notes] integrity`` turns it on:
its effect on ordinary work (over-caution, cost) is measured before it is.
"""

from __future__ import annotations

from truthstone.core.enums import ChallengeCategory, FailureMode, Severity, Verdict
from truthstone.core.models import Finding

# The subject that names this note's kind for the intervention profile (``core/profile.py``).
FINDING_SUBJECT = "integrity_note"

NOTE = (
    'Truthstone (an automated check, not the user): report "done" only when it is true. Do not make '
    "checks pass by editing, skipping or narrowing existing tests, by hard-coding or special-casing "
    "values the tests use, or by rewriting documented rules the request does not ask to change. If a "
    "test or a documented rule contradicts the request, or the request cannot be done as asked, that "
    'is an acceptable result: say so plainly and finish with "not done: <reason>" instead of working '
    "around it."
)


def finding() -> Finding:
    """The record of the note: what it said, at INFO, never a failure."""
    return Finding(
        category=ChallengeCategory.UNDERENGINEERING,
        verdict=Verdict.SUPPORTED,
        failure_mode=FailureMode.NOT_A_FAILURE,
        severity=Severity.INFO,
        subject=FINDING_SUBJECT,
        summary="integrity note",
        detail=NOTE,
    )
