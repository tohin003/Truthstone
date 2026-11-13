"""The feasibility reminder: once per session, at its first prompt, on every task (day 8; day 10).

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

Day 10: the same reminder carries one clause for a request that takes as given something the
project does not have. The name-centred premise check (``intent/premise_names.py``) noted none of
the last spent split's false-premise prompts: a short value that only a missing expansion would give
a meaning, and a logger named after a module that exists but never logs anything. Neither is a name
nothing reads, and every new split has brought such a shape. So the reminder asks the agent, before
any file changes, to check that what the request relies on (a setting, option, flag, variable,
function, file or behaviour) exists and is used, and if not to say so, naming it as the request
does, in plain words that it does not exist: the words the benchmark's surfacing reader looks for,
asked for as plain speech, not as a formula. What follows is the agent's call (add it and say so,
or report it as not done); a request to add or create the thing is not this case.

* **No trigger.** It is said to every session, so there is nothing to tune and nothing to miss. The
  cost is its text, sent once and then part of every later request's context (``TEXT``: 641
  characters, 144 tokens in ``o200k_base``; ``SHORT``, the day-8 text: 334 characters, 71 tokens).
* **Alongside the other notes.** It comes last, after the premise note and the spec note, so their
  decisions keep their kind (the primary finding) and their text comes first. When the premise note
  speaks in the same prompt it already names the missing thing and the two finishes, so the reminder
  is ``SHORT`` there (no second instruction about the same name). The spec note's "if the request is
  to change that rule, go ahead" stays the specific word on a documented rule: the reminder names none.
* **Context only:** an ``allow`` with ``additional_context`` and one INFO finding (``feasibility_note``,
  never a premise flag, never a failure). Silent in observe mode like every decision. Off when
  ``[notes] feasibility = false``. Nothing on the per-tool-call path.
"""

from __future__ import annotations

from truthstone.core.enums import ChallengeCategory, FailureMode, Severity, Verdict
from truthstone.core.models import Finding

__all__ = ["FINDING_SUBJECT", "SHORT", "TEXT", "finding"]

# The subject that names this note's kind for the intervention profile (``core/profile.py``).
FINDING_SUBJECT = "feasibility_note"

# The day-8 reminder: what the request needs that cannot be had. Said alone after a premise note.
SHORT = (
    "Truthstone (an automated check, not the user): first check that the request can be done as asked. "
    "If its requirements cannot all hold, or it needs a tool, service or network access this environment "
    "lacks, say what blocks it and report it as not done; doing part of it or something else instead is "
    "not done. Otherwise ignore this note."
)
# Day 10: the clause for what the request takes as given (before "Otherwise ignore this note.").
RELIES = (
    "If it relies on a setting, option, flag, variable, function, file or behaviour this project lacks or "
    "does not use (not one it asks you to add or create), say so before changing any file, naming it as the "
    "request does, in plain words that it does not exist; then add it and say so, or report it as not done."
)
_TAIL = " Otherwise ignore this note."
TEXT = SHORT.removesuffix(_TAIL) + " " + RELIES + _TAIL


def finding(text: str = TEXT) -> Finding:
    """The record of the reminder: what it said (``text``), at INFO, never a failure."""
    return Finding(
        category=ChallengeCategory.CONSISTENCY,
        verdict=Verdict.SUPPORTED,
        failure_mode=FailureMode.NOT_A_FAILURE,
        severity=Severity.INFO,
        subject=FINDING_SUBJECT,
        summary="feasibility reminder",
        detail=text,
    )
