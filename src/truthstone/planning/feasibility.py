"""The feasibility reminder: once per session, at its first prompt, on every task (day 8).

Three blind probes in a row each brought an impossible task of a shape no rule knew (requirements
that cannot all hold, a tool that is not there), and the gate tolerates none. Rules that recognise
one shape at a time do not converge. What has worked across every probe is a prompt-time note that
makes the agent check before it starts: the spec note (``planning/spec_note.py``) took IMP-SPEC from
frequent misses to none, and the day-3 blanket note (``planning/integrity.py``) gave 6/6 refusals
on impossible tasks. That note was rejected because it PROHIBITED test edits, and agents then
refused legitimate test updates. This reminder forbids nothing: it names the two ways a request can
be impossible (requirements that cannot all hold; a tool, service or network access the environment
lacks, which a name missing from the code is not), says that part of the work or a substitute for
it is not the request done, and asks the agent to ignore it otherwise.

* **No trigger.** It is said to every session, so there is nothing to tune and nothing to miss. The
  cost is its text, sent once and then part of every later request's context (``TEXT``: 334
  characters, 71 tokens in ``o200k_base``).
* **Alongside the other notes.** It comes last, after the premise note and the spec note, so their
  decisions keep their kind (the primary finding) and their text comes first. It names neither a
  missing name nor a documented rule: the premise note's "build it, and say so" and the spec note's
  "if the request is to change that rule, go ahead" stay the specific word on those cases.
* **Context only:** an ``allow`` with ``additional_context`` and one INFO finding (``feasibility_note``,
  never a premise flag, never a failure). Silent in observe mode like every decision. Off when
  ``[notes] feasibility = false``. Nothing on the per-tool-call path.
"""

from __future__ import annotations

from truthstone.core.enums import ChallengeCategory, FailureMode, Severity, Verdict
from truthstone.core.models import Finding

__all__ = ["FINDING_SUBJECT", "TEXT", "finding"]

# The subject that names this note's kind for the intervention profile (``core/profile.py``).
FINDING_SUBJECT = "feasibility_note"

TEXT = (
    "Truthstone (an automated check, not the user): first check that the request can be done as asked. "
    "If its requirements cannot all hold, or it needs a tool, service or network access this environment "
    "lacks, say what blocks it and report it as not done; doing part of it or something else instead is "
    "not done. Otherwise ignore this note."
)


def finding() -> Finding:
    """The record of the reminder: what it said, at INFO, never a failure."""
    return Finding(
        category=ChallengeCategory.CONSISTENCY,
        verdict=Verdict.SUPPORTED,
        failure_mode=FailureMode.NOT_A_FAILURE,
        severity=Severity.INFO,
        subject=FINDING_SUBJECT,
        summary="feasibility reminder",
        detail=TEXT,
    )
