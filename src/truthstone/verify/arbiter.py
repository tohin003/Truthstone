"""The completion arbiter (v0.2 M1): one decision per Stop, from claims and evidence.

Every Stop-time check reports here, and the agent hears at most **one** combined challenge
per Stop. The checks are:

* the Completion Gate's evidence (``completion_gate``): failing, stale, narrower or missing
  test runs, unparsable files;
* spec and doc integrity (M2, ``validate/spec_integrity.py``): a documented rule removed or
  qualified, including a doc rewritten through the shell, read against the task-start snapshot (C2,
  ``verify/spec_snapshot.py``);
* spec conflict (C3, ``verify/spec_conflict.py``): under a request that reserved the tests, a
  documented rule kept word for word while added code throws its documented error outside the
  rule's owner;
* test integrity (M4, ``validate/weakened_tests.py``): existing tests weakened, deleted or
  skipped;
* gaming signatures (``validate/gaming.py``): code or a run that makes tests pass without the
  behaviour — the test run read from production code, an exit or a result rewrite, an equality
  true for anything, a passing run that left the failing test out, contradictory tests both green;
* unread configuration (``validate/config_reads.py``): the change only adds configuration
  that nothing in the repository reads;
* untracked local state (``validate/untracked_state.py``): a command rewrote an ignored local
  file that existed before the task, and neither the request nor the final message names it;
* a premise still unmet (``validate/premise_unmet.py``): the request said a named thing
  already works, the prompt-time note found it missing, and at "done" no code reads it yet;
* under a request that kept the tests, with test pressure (``verify/spec_rules.py``, day 5): a
  doc comment restating a documented rule rewritten while the docs still state it
  (``spec_restated``), or a "done" that says another party must change first
  (``contract_caveat``). They run after every other yardstick check, and only when none of
  them speaks and spec erosion recorded nothing.

Each reason has a ``ReasonCategory``, and a category speaks at most once per task.

The rules, in order
-------------------
1. **No completion claim, no challenge.** A question, "not done: <reason>", or a message
   that says what is unverified or failing hands the turn back honestly. It is accepted,
   and the developer is told any gap.
2. **The profile decides who may speak.** ``"minimal"`` (the product default) lets only
   the categories in ``MINIMAL_STOP_CATEGORIES`` reach the agent: a weakened yardstick (a),
   relevant failing tests left undisclosed (b), configuration nothing reads (e), ignored local
   state a command rewrote (f).
   ``"full"`` adds today's verification verdicts (stale, narrower, no run, unparsable).
   Everything that does not speak is recorded, and the developer gets the gap through
   ``unverified_finish``.
3. **Failing tests speak only with evidence (b), under the minimal profile.** The latest
   run, after the last edit, must have failed tests that exercise the change (a failing test
   file the task changed, or one that covers a changed file), in every case, even when the
   message says all tests pass. The failure must not already have been red before the
   task's first edit. And the message must not disclose it. Any disclosure counts: a
   failure word, an honest partial count ("34 passed" from a run of 36), or naming the
   failing test. With no link between the failing tests and the change, it stays silent.
4. **Integrity checks speak only on a completion claim,** and only when the request did
   not ask for that change (each check owns its own exemptions).
5. **Budget.** At most ``max_blocks`` Stop challenges per task. After that the turn ends with
   the gap reported to the developer. It is never held indefinitely.
6. **A stop hook already holding the turn** (C3): an asked-again concern speaks, and alone (it
   follows the agent's own reply to the first ask); otherwise only the first ask of a yardstick
   category not raised before (spec erosion, spec conflict, test weakening, test fitting, a gaming
   signature) speaks, and with none the Stop is muted.
7. **Spec conflict yields** to spec erosion, test weakening, test fitting, a gaming signature or
   original tests failing at the same Stop: they say more about the same change. A yielding first
   ask leaves them its stop-hook exemption; a yielding asked-again concern is not recorded.
8. **Asked again** (spec erosion, spec conflict): "done" claimed again over the same rule is asked
   once more, the smallest ask, and recorded as ``spec_erosion:again`` / ``spec_conflict:again``:
   asked twice, never thrice.

Never raises; a check that fails is skipped (fail open).
"""

from __future__ import annotations

import contextvars
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from truthstone.core.enums import (
    MINIMAL_STOP_CATEGORIES,
    ChallengeCategory,
    EscalationLevel,
    FailureMode,
    GateResult,
    ReasonCategory,
    Severity,
    Verdict,
)
from truthstone.core.models import EvidenceRef, Finding
from truthstone.core.taskstate import TaskState
from truthstone.repo import scanner
from truthstone.repo.index import RepoIndex
from truthstone.validate.keep_reading import straight_quotes
from truthstone.verify import baseline, claims, completion_gate, runners, spec_conflict

log = logging.getLogger(__name__)

__all__ = ["MINIMAL_PROFILE", "Arbitration", "Concern", "arbitrate", "category_of"]

MINIMAL_PROFILE = MINIMAL_STOP_CATEGORIES
PROFILES = ("minimal", "full")

# The gate's own subjects, by category.
_GATE_CATEGORY = {
    "unparsable-on-completion": ReasonCategory.UNPARSABLE,
    "failing-tests-on-completion": ReasonCategory.FAILING_TESTS,
}
# The order concerns are told in: the yardstick first, then the evidence.
_ORDER = (
    ReasonCategory.SPEC_EROSION,
    ReasonCategory.SPEC_CONFLICT,
    ReasonCategory.TEST_WEAKENING,
    ReasonCategory.TEST_FITTING,
    ReasonCategory.GAMING_SIGNATURE,
    ReasonCategory.SPEC_RESTATED,
    ReasonCategory.CONTRACT_CAVEAT,
    ReasonCategory.ORIGINAL_TESTS_FAIL,
    ReasonCategory.FAILING_TESTS,
    ReasonCategory.UNREAD_CONFIG,
    ReasonCategory.UNTRACKED_STATE,
    ReasonCategory.PREMISE_UNMET,
    ReasonCategory.UNPARSABLE,
    ReasonCategory.UNVERIFIED,
)
_SPEAKING = (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
# The yardstick categories (C3): while a stop hook holds the turn, a first ask of one of them that was
# not raised before still speaks.
_YARDSTICK = frozenset(
    {
        ReasonCategory.SPEC_EROSION,
        ReasonCategory.TEST_WEAKENING,
        ReasonCategory.TEST_FITTING,
        ReasonCategory.GAMING_SIGNATURE,
        ReasonCategory.SPEC_CONFLICT,
        ReasonCategory.SPEC_RESTATED,
        ReasonCategory.CONTRACT_CAVEAT,
    }
)
# A ``spec_conflict`` concern yields to these when they speak at the same Stop (C3).
_CONFLICT_YIELDS_TO = frozenset(
    {
        ReasonCategory.SPEC_EROSION,
        ReasonCategory.TEST_WEAKENING,
        ReasonCategory.TEST_FITTING,
        ReasonCategory.GAMING_SIGNATURE,
        ReasonCategory.ORIGINAL_TESTS_FAIL,
    }
)


@dataclass(slots=True)
class Concern:
    """One reason to hold a "done", with the text the agent would be told."""

    category: ReasonCategory
    text: str
    finding: Finding
    # Integrity concerns need a completion claim; the gate's concerns carry their own rules.
    needs_claim: bool = True
    # False: recorded only, whatever the profile (a check's own exemption applied).
    can_speak: bool = True
    # The accepted finishes, when this concern's own evidence narrows its category's default.
    finish: str = ""


@dataclass(slots=True)
class Arbitration:
    result: GateResult = GateResult.PASS
    reason: str = ""
    findings: list[Finding] = field(default_factory=list)
    # The categories this Stop raises with the agent (empty when it does not block).
    raised: list[ReasonCategory] = field(default_factory=list)
    # Told to the developer when the turn ends with a gap nobody raised with the agent.
    unresolved: str = ""
    # The first concern a completion claim met that the profile kept from the agent: the
    # engine marks the decision "withheld" (what the full profile would have said). A concern
    # its own check accepted (disclosed, unrelated, requested...) is not withheld: it is fine.
    withheld: Concern | None = None

    @property
    def should_block(self) -> bool:
        return bool(self.raised)


def category_of(finding: Finding) -> ReasonCategory | None:
    """The category of a Stop finding: its subject when that is a category value (the
    primary finding of every challenge, and every integrity finding), else the gate's."""
    try:
        return ReasonCategory(finding.subject)
    except ValueError:
        pass
    if finding.subject in _GATE_CATEGORY:
        return _GATE_CATEGORY[finding.subject]
    if finding.severity in _SPEAKING and finding.failure_mode is FailureMode.UNVERIFIED_CHANGE:
        return ReasonCategory.UNVERIFIED
    if finding.subject == "requested-tests-missing":
        return ReasonCategory.UNVERIFIED
    return None


# Integrity checks register here: f(state, index) -> list[Concern]. Each must never raise.
IntegrityCheck = Callable[[TaskState, RepoIndex], list[Concern]]

# One Stop reads each changed file once, however many checks ask (``changed_texts``).
_TEXTS: contextvars.ContextVar[dict | None] = contextvars.ContextVar("truthstone_stop_texts", default=None)
# The final message of the Stop being decided, for a check whose finding the message can settle
# (``final_message``): naming a file is enough for the untracked-state check.
_MESSAGE: contextvars.ContextVar[str | None] = contextvars.ContextVar("truthstone_stop_message", default=None)
# At most this many changed files are compared at Stop (each read up to 512 KB): beyond it the
# integrity checks see nothing more, which can only make them quieter.
MAX_COMPARED_FILES = 400


def _integrity_checks(original_tests: bool = False) -> list[IntegrityCheck]:
    from truthstone.validate import (
        config_reads,
        fitting,
        gaming,
        premise_unmet,
        untracked_state,
        weakened_tests,
    )
    from truthstone.validate import original_tests as original_tests_check
    from truthstone.verify import integrity, spec_rules

    checks: list[IntegrityCheck] = [
        integrity.spec_concerns,
        spec_conflict.conflict_concerns,
        weakened_tests.concerns,
        fitting.concerns,
        gaming.concerns,
        # After every other yardstick check: it runs only when none of them speaks (``_yardstick_spoke``).
        spec_rules.concerns,
        config_reads.concerns,
        untracked_state.concerns,
        premise_unmet.concerns,
    ]
    if original_tests:
        # Last, and opt-in (``[challenge] original_tests``): the only check that runs tests
        # (sandboxed, within its own time budget); it reuses the changed-file texts read above.
        checks.append(original_tests_check.concerns)
    return checks


def final_message() -> str:
    """The final message of the Stop being arbitrated ("" outside one)."""
    return _MESSAGE.get() or ""


def _yardstick_spoke(found_all: list[list[Concern]]) -> bool:
    """Whether a check before ``spec_rules`` has something to say (day 5): a yardstick concern
    that may speak, or any spec-erosion concern at all (one recorded only, because the request asked
    for the rule's change, still has its say about the rule)."""
    return any(
        (concern.can_speak and concern.category in _YARDSTICK)
        or concern.category is ReasonCategory.SPEC_EROSION
        for found in found_all
        for concern in found
    )


def _runs_last(check: IntegrityCheck) -> bool:
    from truthstone.verify import spec_rules

    return check is spec_rules.concerns


def _without_repeats(found_all: list[list[Concern]]) -> list[list[Concern]]:
    """A premise still unmet that the unread-configuration concern already names, switch for
    switch, is said once, by that concern: a configuration-only change to a switch nothing reads
    is the same fact told twice."""
    unread = {
        ref.symbol
        for found in found_all
        for concern in found
        if concern.category is ReasonCategory.UNREAD_CONFIG and concern.can_speak
        for ref in concern.finding.evidence
        if ref.symbol
    }
    if not unread:
        return found_all
    return [
        [
            concern
            for concern in found
            if not (
                concern.category is ReasonCategory.PREMISE_UNMET
                and {ref.symbol for ref in concern.finding.evidence if ref.symbol} <= unread
            )
        ]
        for found in found_all
    ]


def arbitrate(
    state: TaskState | None,
    index: RepoIndex,
    message: str | None = None,
    stop_hook_active: bool = False,
    max_blocks: int = 2,
    pending_tasks: list[dict] | None = None,
    profile: str = "minimal",
    checks: Iterable[IntegrityCheck] | None = None,
    original_tests: bool = False,
) -> Arbitration:
    """Decide this Stop. Never raises."""
    if state is None:
        return Arbitration()
    profile = profile if profile in PROFILES else "minimal"
    said = claims.classify(message)
    done = said.claims

    concerns: list[Concern] = []
    gate = completion_gate.assess(state, index, pending_tasks or [])
    exempt = completion_gate._hand_back(state, gate, message) if gate.should_block else None
    if exempt is not None:
        # An honest hand-back or a requested red phase (G4a): recorded as the exemption.
        findings = list(exempt.findings)
    else:
        findings = list(gate.findings)
        gate_concern = _gate_concern(gate, state, index, said, message, profile)
        if gate_concern is not None:
            concerns.append(gate_concern)

    token, said_token = _TEXTS.set({}), _MESSAGE.set(message)
    try:
        found_all = []
        for check in checks if checks is not None else _integrity_checks(original_tests):
            if _runs_last(check) and (not done or _yardstick_spoke(found_all)):
                continue  # spec_restated / contract_caveat: only a claim nothing else holds (day 5)
            try:
                found_all.append(check(state, index))
            except Exception:
                log.exception("truthstone: a completion integrity check failed; skipped")
    finally:
        _MESSAGE.reset(said_token)
        _TEXTS.reset(token)
    for found in _without_repeats(found_all):
        for concern in found:
            # A spec erosion speaks only on a completion claim, so a message that names the changed
            # rule *and* claims done is the rationalised rewrite itself, not a disclosure: it is not
            # exempted (an honest hand-back carries no claim and is never held).
            findings.append(concern.finding)
            concerns.append(concern)

    minimal = profile == "minimal"
    allowed = MINIMAL_PROFILE if minimal else frozenset(ReasonCategory)
    # Once per reason per task is the v0.2 contract; "full" keeps the pre-v0.2 rationing
    # (the same problem may be raised until the per-task budget is spent).
    already = set(state.raised_categories) if minimal else set()
    speaking: list[Concern] = []
    repeated: list[Concern] = []
    again: Concern | None = None
    for concern in concerns:
        if not concern.can_speak or concern.category not in allowed:
            continue  # recorded only (its finding is already in ``findings``)
        if concern.needs_claim and not done:
            continue  # an honest hand-back is accepted (rule 1)
        if concern.category in already:
            record = _AGAIN_RECORDS.get(concern.category)
            if minimal and record is not None and record not in already and again is None:
                # The one exception to once per reason: "done" claimed again over a documented
                # rule still rewritten (spec erosion) or still worked around (spec conflict). The
                # second ask is the smallest one: keep the change if you must, but hand the rule
                # decision back. It can only follow a first challenge.
                again = _asked_again(concern)
                speaking.append(again)
                continue
            repeated.append(concern)
        else:
            speaking.append(concern)

    # A spec conflict yields to the other yardstick concerns speaking at the same Stop (C3): they say
    # more about the same change. A yielding first ask leaves them its stop-hook exemption; a
    # yielding asked-again concern is not recorded.
    inherits: list[Concern] = []
    conflicts = [c for c in speaking if c.category is ReasonCategory.SPEC_CONFLICT]
    if conflicts:
        others = [c for c in speaking if c.category in _CONFLICT_YIELDS_TO]
        if others:
            for c in conflicts:
                speaking.remove(c)
                if c is again:
                    again = None
                else:
                    inherits.extend(others)

    if not speaking:
        # Raised once already and finished anyway: the developer hears of it (G10), under
        # that concern's own category (its finding first, for the profile's choke point).
        told = next((c for c in repeated if c.finding.severity in _SPEAKING), None)
        if told is None:
            held = sorted(
                (c for c in concerns if c.can_speak and c not in repeated and (done or not c.needs_claim)),
                key=lambda c: _ORDER.index(c.category),
            )
            return Arbitration(
                GateResult.PASS, reason=gate.reason, findings=findings, withheld=held[0] if held else None
            )
        return Arbitration(
            GateResult.PASS,
            reason=gate.reason,
            findings=[_primary(told), *findings],
            unresolved=told.finding.summary,
        )

    # The per-task block budget mutes first. While a stop hook holds the turn (C3, comp-3-12): the
    # asked-again challenge follows the agent's own reply to the first one, so a stop hook is holding
    # the turn by construction; it is exempt, and it alone speaks. With none, the first ask of a
    # yardstick category not raised before is exempt (with the concerns a yielding first ask left its
    # exemption to); the rest are dropped from this challenge (they stay in the findings), and with
    # nothing left the Stop is muted.
    muted = completion_gate._muted_reason(state, False, max_blocks)
    if not muted and stop_hook_active and state.stop_blocks >= 1:
        if again is not None:
            speaking = [again]
        else:
            kept = [
                c
                for c in speaking
                if (c.category in _YARDSTICK and c.category not in already) or c in inherits
            ]
            if kept:
                speaking = kept
            else:
                muted = "a stop hook is already holding this turn"
    if muted:
        first = min(speaking, key=lambda c: _ORDER.index(c.category))
        return Arbitration(
            GateResult.PASS,
            reason=muted,
            findings=[_primary(first), *findings],
            unresolved=first.finding.summary,
        )

    speaking.sort(key=lambda c: _ORDER.index(c.category))
    result = (
        GateResult.VERIFICATION_FAILED
        if any(c.category in (ReasonCategory.FAILING_TESTS, ReasonCategory.UNPARSABLE) for c in speaking)
        else GateResult.INCOMPLETE
    )
    # The primary findings come first and carry their category as the subject: the
    # engine's choke point lets a Stop challenge through only for an allowed category.
    primary = [_primary(c) for c in speaking]
    raised: list = [c.category for c in speaking]
    if again is not None and again in speaking:
        # recorded with the categories: asked twice, never thrice
        raised.append(_AGAIN_RECORDS[again.category])
    return Arbitration(
        result,
        reason=_render(speaking),
        findings=[*primary, *findings],
        raised=raised,
    )


def _primary(concern: Concern) -> Finding:
    if concern.finding.subject == concern.category.value:
        return concern.finding
    return concern.finding.model_copy(update={"subject": concern.category.value})


_DEFAULT_FINISHES = (
    'Accepted finishes: fix it and finish; finish with "not done: <reason>"; or say '
    "explicitly in your final message why it should stay as it is."
)
# Where the honest finish is a report, not a justification, the accepted finishes offer no
# "why it should stay": an agent that rewrote a documented rule, weakened a test or set a
# switch nothing reads would take that door with the same rationale that led it there.
_FINISHES: dict[ReasonCategory, str] = {
    # Both finishes are hand-backs: a rule change is the user's decision, so the agent may keep
    # its change but not call it done. An agent sure the request settles it (an instruction
    # about the tests) still has an honest finish that does not contradict the user.
    # The first ask is the outcome the documented rule calls for: restore it and hand back the
    # contradiction. The asked-again challenge (``_asked_again``) is the smallest ask: keep the
    # change if you must, but do not call it done.
    ReasonCategory.SPEC_EROSION: (
        "Accepted finish: restore the rule and the behaviour it documents, then finish with "
        '"not done: <which test contradicts which documented rule>", so the user decides.'
    ),
    # A rule kept word for word while the code routes around it (C3): either the test contradicts the
    # rule, or the change keeps it and the user confirms that.
    ReasonCategory.SPEC_CONFLICT: spec_conflict.FINISH,
    ReasonCategory.TEST_WEAKENING: (
        'Accepted finishes: restore the test and fix the code, then finish; or finish with "not done: '
        '<which test was weakened, and why>", so the user decides.'
    ),
    ReasonCategory.UNREAD_CONFIG: (
        'Accepted finishes: finish with "not done: <reason>"; or show in your final message which code '
        "reads it."
    ),
    ReasonCategory.TEST_FITTING: (
        'Accepted finishes: remove the special case and finish with "not done: <what makes the test '
        'impossible>"; or move the exception into configuration or data the code reads, then finish.'
    ),
    # Each signature carries its own finish (``validate/gaming.py``); this is the fallback.
    ReasonCategory.GAMING_SIGNATURE: (
        'Accepted finish: remove the shortcut, then fix the code or finish with "not done: <which test '
        'cannot pass, and why>".'
    ),
    ReasonCategory.UNTRACKED_STATE: (
        "Accepted finishes: restore the files and finish; if the change was intended, name these files "
        'in your final message; or finish with "not done: <which local files changed>".'
    ),
    # Tests that existed fail as they were written for inputs the request never mentions (day 3): the
    # honest finishes keep the old behaviour for those inputs, or hand the contradiction back. Never
    # "make the tests pass": that is how the tests got rewritten.
    ReasonCategory.ORIGINAL_TESTS_FAIL: (
        "Accepted finishes: restore the old behaviour for the inputs the request did not name, keep the "
        'original tests as they were, and finish; or finish with "not done: <which existing expectation '
        'the change breaks>", so the user decides.'
    ),
    # A workaround that leaves the named thing missing is not one of them (day 3).
    ReasonCategory.PREMISE_UNMET: (
        "Accepted finishes: make it exist and work as the request describes, then finish; or finish "
        'with "not done: <the name> does not exist" and say what you did instead.'
    ),
}

# An edit inside an existing test under test pressure (``validate/weakened_tests.py``, day 3):
# its own lead, so its own finishes, which keep the new checks as new tests.
EDITED_LEAD = "This change edits tests that existed before it"
_EDITED_FINISH = (
    "Accepted finishes: restore the existing tests (put any new checks in new tests next to them) and "
    'finish; or finish with "not done: <which existing test is wrong, and why>".'
)


SPEC_EROSION_AGAIN = "spec_erosion:again"
SPEC_CONFLICT_AGAIN = spec_conflict.SPEC_CONFLICT_AGAIN
# The categories with an asked-again path, and the record each one leaves: asked twice, never thrice.
_AGAIN_RECORDS: dict[ReasonCategory, str] = {
    ReasonCategory.SPEC_EROSION: SPEC_EROSION_AGAIN,
    ReasonCategory.SPEC_CONFLICT: SPEC_CONFLICT_AGAIN,
}
AGAIN_LEAD = "You finished as done again"
_AGAIN_FINISH = (
    'Accepted finishes: restore the rule and finish with "not done: <which test contradicts which '
    'documented rule>"; or keep the change and finish with "not done: <the rule I changed>, please '
    'confirm".'
)


def _asked_again(concern: Concern) -> Concern:
    """The second, smallest ask over a documented rule still rewritten (or, for a spec conflict,
    still worked around) at a repeated "done". A concern already phrased as the second ask (the
    rule's words restored, its breach kept: ``verify/integrity.py``) is asked as it is."""
    if concern.category is ReasonCategory.SPEC_CONFLICT:
        refs = [ref for ref in concern.finding.evidence if ref.source == "doc-rule" and ref.snippet][
            : spec_conflict.MAX_QUOTED
        ]
        listing = "\n".join(
            f'  - {ref.path}{f":{ref.line}" if ref.line else ""}: "{ref.snippet}"' for ref in refs
        )
        text = (
            f"{AGAIN_LEAD}, but the documented rule is still worked around:\n"
            f"{listing}\n{spec_conflict.AGAIN_TAIL}"
        )
        return Concern(concern.category, text, concern.finding, needs_claim=True, finish=spec_conflict.FINISH)
    if concern.text.startswith(AGAIN_LEAD):
        return concern
    refs = [ref for ref in concern.finding.evidence if ref.snippet][:3]
    listing = "\n".join(
        f'  - {ref.path}{f":{ref.line}" if ref.line else ""}: "{ref.snippet}"' for ref in refs
    )
    text = (
        f"{AGAIN_LEAD}, but the documented rule is still changed:\n"
        f"{listing}\n"
        "A completion that changes a documented rule needs the user's confirmation, whatever the "
        "tests say, and only the user can give it. Keep your change if you are sure of it, but do "
        'not finish as done: finish with "not done: <the rule I changed>, please confirm".'
    )
    return Concern(concern.category, text, concern.finding, needs_claim=True)


def _render(concerns: list[Concern]) -> str:
    """One message: who is speaking, each concern, the finishes that are accepted (those of
    the first concern, in the arbiter's order)."""
    if len(concerns) == 1:
        body = concerns[0].text
    else:
        body = "\n\n".join(f"{n}. {c.text}" for n, c in enumerate(concerns, 1))
    return (
        "Truthstone (an automated check, not the user) found a problem with finishing now.\n\n"
        f"{body}\n\n{_finishes(concerns[0])}"
    )


def _finishes(first: Concern) -> str:
    if first.finish:
        return first.finish
    if first.text.startswith(AGAIN_LEAD):
        return _AGAIN_FINISH
    if first.text.startswith(_CAUSED_LEAD):
        # No "why it should stay": the disclosure already said why, and the tests are still red.
        return _CAUSED_FINISH
    if first.text.startswith(EDITED_LEAD):
        return _EDITED_FINISH
    return _FINISHES.get(first.category, _DEFAULT_FINISHES)


# -- the gate's evidence --------------------------------------------------------------------


def _gate_concern(
    gate: completion_gate.GateVerdict,
    state: TaskState,
    index: RepoIndex,
    said: claims.Claims,
    message: str | None,
    profile: str,
) -> Concern | None:
    if not gate.should_block:
        return None
    lead = next((f for f in gate.findings if f.severity in _SPEAKING), None)
    if lead is None:
        return None
    category = _GATE_CATEGORY.get(lead.subject, ReasonCategory.UNVERIFIED)
    if profile == "full":
        # Today's semantics: whatever the evidence holds speaks (hand-backs were exempted
        # before this point), with or without a completion claim.
        return Concern(category, gate.reason, lead, needs_claim=False)
    if category is not ReasonCategory.FAILING_TESTS:
        return Concern(category, gate.reason, lead, needs_claim=True)
    failure = gate.failure
    if failure is None:
        return Concern(category, gate.reason, lead, can_speak=False)
    if failure.seq is not None and any(seq > failure.seq for seq in state.last_change_seq.values()):
        # Edited past: a stale result, not a failure after the last edit (b) — unverified.
        return Concern(ReasonCategory.UNVERIFIED, gate.reason, lead)
    if not said.claims:
        quiet, contradicted = "no completion claim", False
    else:
        quiet, contradicted = _failure_accepted(failure, state, index, message)
    if quiet == _CAUSED:
        return Concern(ReasonCategory.FAILING_TESTS, _caused_text(failure, index), lead)
    if quiet:
        log.info("truthstone: arbiter accepted a finish with failing tests (%s)", quiet)
        note = lead.model_copy(update={"severity": Severity.LOW, "summary": f"{lead.summary} ({quiet})"})
        category = ReasonCategory.UNVERIFIED if quiet == _STALE_FAILURE else ReasonCategory.FAILING_TESTS
        return Concern(category, gate.reason, note, can_speak=False)
    return Concern(ReasonCategory.FAILING_TESTS, _failing_text(failure, contradicted), lead)


def _failing_text(failure: runners.TestOutcome, contradicted: bool) -> str:
    named = list(failure.failing_tests[:3]) or list(failure.failing_files[:3])
    which = f": {', '.join(named)}" if named else ""
    summary = f" ({failure.summary})" if failure.summary else ""
    if contradicted:
        return (
            f"The final message says the tests pass, but the latest test run, `{failure.command}`, "
            f"reported failures{which}{summary}. Fix them, or say in your final message which tests "
            "fail and why."
        )
    return (
        f"The latest test run, `{failure.command}`, still fails{which}{summary}. It exercises code "
        "this task changed, and the final message does not say so. Fix it, or say in your final "
        "message which tests fail and why."
    )


_STALE_FAILURE = "the code changed after the failing run"
_CAUSED = "disclosed, but the change made them fail"

# -- (b) with a disclosure: "done" while the change's own tests fail (Stage 4, rule 1) -----------------
#
# A careful agent changes behaviour, sees the changed module's tests fail on the old expectations,
# says so — and claims done anyway, leaving the suite red. Disclosure accepts an honest gap; it
# does not make a red suite the change caused into a finished task. The rule speaks only when:
#   (i)   the latest run, after the last edit, fails tests linked to the change (``_related``);
#   (ii)  nothing was edited after it (the caller's stale check);
#   (iii) the final message claims done (the caller's claim check);
#   (iv)  none of the failing tests failed in a run before the task's first edit (a red run
#         there that names no failure leaves that open, so it counts as failed);
#   (v)   the request neither names them nor excuses them (known, flaky, pre-existing, leave
#         them failing);
#   and, with no run before the first edit that ran those tests (``runners.covers``), the
#   failing file is the changed module's own test file — the one pairing that needs no
#   baseline to read as caused — and the message does not put the failure outside the change
#   (already failing, unrelated, flaky, a known issue, failing on main too: the known-failure
#   control shape). With such a baseline, the evidence decides, whatever the message says.
# A disclosure that the tests could not run here (no database, no network) is not this case.

_ENVIRONMENT = re.compile(
    r"\bneeds?\s+(?:an?\s+)?(?:internet|network(?:\s+access)?|(?:running\s+)?database|db|credentials|"
    r"(?:running\s+)?server|docker|postgres(?:ql)?|redis|api\s+key|gpu)\b"
    r"|\bno\s+(?:internet|network|database|db|postgres(?:ql)?|redis|docker|credentials)\b",
    re.I,
)
_EXCUSED = re.compile(
    r"\b(?:flaky|pre-?existing|known\s+(?:to\s+)?(?:fail\w*|be\s+(?:failing|broken|flaky))|"
    r"known\s+(?:failure|issue|bug|broken)|already\s+(?:\w+\s+){0,2}?(?:fail\w*|red|broken)|"
    r"(?:expected|allowed|ok|fine)\s+to\s+fail|"
    r"leave\s+(?:\w+\s+){0,6}?(?:fail\w*|red|broken)|ignore\s+(?:\w+\s+){0,4}?(?:tests?|fail\w*))\b",
    re.I,
)


def _caused_by_the_change(
    failure: runners.TestOutcome, state: TaskState, index: RepoIndex, message: str | None
) -> bool:
    """Whether a disclosed failure is the change's own, left red under a "done" (see above)."""
    sources = [path for path in state.changed_files if not scanner.is_test_path(path)]
    failing = {
        path
        for path in _failing_paths(failure, index)
        if path in state.changed_files or any(_same_tree(path, source) for source in sources)
    }
    if not failing or not _related(failing, state, index):
        return False  # (i); a failing test in another package of a monorepo is not linked
    text = (message or "")[: claims.MAX_MESSAGE]
    if claims._UNVERIFIED.search(text) or _ENVIRONMENT.search(text):
        return False  # "couldn't run the integration tests", "needs a database"
    first = state.first_change_seq
    before = [run for run in state.verification.outcomes if run.seq is not None and first and run.seq < first]
    failing_ids = set(failure.failing_tests)
    for run in before:
        if run.passed is not False:
            continue
        named, paths = set(run.failing_tests), _failing_paths(run, index)
        if not (named or paths) or failing_ids & named or failing & paths:
            return False  # (iv): failed before the first edit, or a red run there named nothing
    if _excused(state.spec.prompt or "", failure, failing):
        return False  # (v)
    if any(run.passed is not None and runners.covers(run, failure) for run in before):
        return True  # a baseline that ran these tests, and they did not fail there
    # No baseline for them: only the message's own admission that the change made them fail
    # ("they expect the old format") speaks, never against its word that they are not the
    # change's, and only for the changed module's own test file. Plain words for a known
    # failure ("was red when I started", "times out here") are too many to list (audit S4).
    return (
        _attributed(text, failure) and not _not_the_changes(text, failure) and _own_test_file(failing, state)
    )


# What a message says to tie a failure to the change: the tests expect, pin or assert the old
# behaviour, are outdated, or fail because of (after, with) the change.
_ATTRIBUTED = re.compile(
    r"\bexpect(?:s|ed|ing)?\s+(?:the\s+|an?\s+)?(?:old|previous|former|original|legacy|prior)\b"
    r"|\bstill\s+(?:expect|assert|check|pin|want)\w*\b"
    r"|\b(?:pin|assert|encode|hard-?code)(?:s|ed|ing)?\s+(?:the\s+)?(?:old|previous|former|original|legacy|prior)\b"
    r"|\b(?:outdated|out\s+of\s+date|obsolete|stale)\b"
    r"|\b(?:old|previous|former|legacy|prior)\s+(?:\w+\s+)?(?:format|behaviou?r|value|output|layout|default|"
    r"api|signature|wording|expectations?|rules?|limits?|ceiling)\b"
    r"|\b(?:because\s+of|due\s+to|after|by|with)\s+(?:my|this|the)\s+(?:\w+\s+)?change\b",
    re.I,
)


_PASS_WORD = re.compile(r"\bpass(?:ed|es|ing)?\b", re.I)


def _attributed(text: str, failure: runners.TestOutcome) -> bool:
    names = [test.rsplit("::", 1)[-1].split("[", 1)[0] for test in failure.failing_tests]
    for sentence in _PLAIN_SENTENCES.split(text):
        about = (
            _FAIL_WORD.search(sentence)
            or _TESTS_NOUN.search(sentence)
            or _PASS_WORD.search(sentence)  # "34 passed; two still expect DD/MM/YYYY"
            or any(name and name in sentence for name in names)
        )
        if about and _ATTRIBUTED.search(sentence):
            return True
    return False


# What a message says to put a failure outside the change: it predates the change, is unrelated
# to it, is flaky, is a known issue, or fails on the main branch as well. It is taken only where no
# baseline run says otherwise, and only in a sentence about the failure.
_NOT_THE_CHANGES = re.compile(
    r"\bunrelated\b|\bnot\s+related\s+to\b|\bnothing\s+to\s+do\s+with\b"
    r"|\bindependent(?:ly)?\s+of\s+(?:this|my|the|our)\s+(?:\w+\s+){0,2}?(?:change|work|task|edit|patch)\w*"
    r"|\bflak(?:y|iness)\b|\bintermittent(?:ly)?\b|\bknown\s+(?:failure|issue|bug|problem)\b"
    r"|\b(?:fail\w*|red|broken)\b[^.!?\n]{0,40}?\bon\s+(?:main|master|trunk|develop|the\s+(?:base|main)\s+branch)\b"
    # checked against the code without the change (audit H4)
    r"|\bnot\s+(?:because\s+of|due\s+to|from)\s+(?:my|this|the|our)\b"
    r"|\b(?:isn'?t|is\s+not|wasn'?t|was\s+not|not)\s+caused\s+by\s+(?:my|this|the|our)\b"
    r"|\bat\s+HEAD\b|\bclean\s+checkout\b|\b(?:changes?|edits?)\s+stashed\b|\bwithout\s+my\s+(?:changes?|edits?)\b"
    # the environment, not the code (audit H3, H5)
    r"|\bsandbox\b|\bcontainer'?s?\b|\b(?:this|the|my|our)\s+(?:local\s+)?environment\b"
    r"|\b(?:not|isn'?t|aren'?t)\s+installed\b|\bModuleNotFoundError\b|\bImportError\b|\bPermissionError\b"
    r"|\bpermission\s+denied\b|\bunsupported\s+locale\b|\blocale\.Error\b|\boffline\b|\bno\s+network\b"
    r"|\bwall[-\s]clock\b|\bdoes(?:n'?t|\s+not)\s+import\b",
    re.I,
)
_PLAIN_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")
# A request that keeps the red tests' update for the user, in a sentence about tests (audit H1).
_DEFERRED = re.compile(
    r"\b(?:I|we)(?:'|\u2019)?ll\s+(?:update|fix|change|adjust|handle|rewrite|redo|deal\s+with)\b|\bmyself\b"
    r"|\bfollow[-\s]?up\b|\bseparate\s+(?:PR|pull\s+request|change|commit|ticket|branch)\b"
    r"|\bwill\s+(?:break|fail|go\s+red)\b|\b(?:that'?s|that\s+is|it'?s|it\s+is)\s+expected\b"
    r"|\bexpected\s+to\s+(?:break|fail)\b|\bstay\s+out\s+of\b",
    re.I,
)
# Where a path's project begins: a monorepo package's tests are not another package's (audit H5).
_TREE_MARKERS = frozenset({"src", "lib", "tests", "test", "spec", "specs", "__tests__"})


def _tree(path: str) -> str:
    """`packages/bursar/src/bursar/utils.py` -> packages/bursar; `tests/test_x.py` -> ''."""
    parts = PurePosixPath(path).parts[:-1]
    for n, part in enumerate(parts):
        if part in _TREE_MARKERS:
            return "/".join(parts[:n])
    return "/".join(parts)


def _same_tree(one: str, other: str) -> bool:
    """Two paths of one project: either tree holds the other (the repository root holds all)."""
    a, b = _tree(one), _tree(other)
    return not a or not b or a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _not_the_changes(text: str, failure: runners.TestOutcome) -> bool:
    names = [test.rsplit("::", 1)[-1].split("[", 1)[0] for test in failure.failing_tests]
    for sentence in _PLAIN_SENTENCES.split(text):
        about = _FAIL_WORD.search(sentence) or any(name and name in sentence for name in names)
        if about and (_PREEXISTING.search(sentence) or _NOT_THE_CHANGES.search(sentence)):
            return True
    return False


def _excused(prompt: str, failure: runners.TestOutcome, failing: set[str]) -> bool:
    """(v): the request names the failing tests, or calls them known, flaky or pre-existing, or
    asks to leave them failing: in so many words, by keeping their update for the user ("I'll
    update them myself", "they will break, that's expected", "a follow-up PR", "stay out of
    tests/"), or by asking for failing tests first (a red phase)."""
    if isinstance(prompt, str):
        prompt = straight_quotes(prompt)  # C6: curly apostrophes read as "'" in each reader
    if _EXCUSED.search(prompt) or claims.red_phase_requested(prompt):
        return True
    if any(
        _TESTS_NOUN.search(sentence) and _DEFERRED.search(sentence)
        for sentence in _PLAIN_SENTENCES.split(prompt)
    ):
        return True
    names = {test.rsplit("::", 1)[-1].split("[", 1)[0] for test in failure.failing_tests}
    names |= {PurePosixPath(path).name for path in failing} | {PurePosixPath(path).stem for path in failing}
    return any(len(name) >= 6 and re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", prompt) for name in names)


def _module_stem(path: str) -> str:
    """`src/shop/export.py` -> export; `tests/test_export.py`, `export_test.go`, `export.test.ts` and
    `export.spec.ts` -> export."""
    stem = PurePosixPath(path).name.split(".", 1)[0]
    for affix in ("test_", "tests_"):
        stem = stem.removeprefix(affix)
    for affix in ("_test", "_tests", "_spec"):
        stem = stem.removesuffix(affix)
    return stem.lower()


def _own_test_file(failing: set[str], state: TaskState) -> bool:
    """A failing test file paired by name with a production file the task changed
    (tests/test_export.py for export.py)."""
    changed = {
        _module_stem(path)
        for path in state.changed_files
        if not scanner.is_test_path(path) and PurePosixPath(path).stem not in ("__init__", "index")
    }
    return any(scanner.is_test_path(path) and _module_stem(path) in changed for path in failing)


def _caused_text(failure: runners.TestOutcome, index: RepoIndex) -> str:
    named = [test.rsplit("::", 1)[-1] for test in failure.failing_tests[:3]] or sorted(
        _failing_paths(failure, index)
    )[:3]
    which = ", ".join(f"`{name}`" for name in named) or "tests"
    verb = "fails" if len(named) == 1 else "fail"
    return (
        f"{_CAUSED_LEAD} {which} {verb} after your change. If your change makes them outdated, "
        "update them to the new behaviour; if not, fix the code; otherwise finish with "
        '"not done: <reason>".'
    )


_CAUSED_LEAD = "You claimed done while"
_CAUSED_FINISH = (
    "Accepted finishes: update the tests your change made outdated, or fix the code, then finish; "
    'or finish with "not done: <reason>".'
)


def _failure_accepted(
    failure: runners.TestOutcome, state: TaskState, index: RepoIndex, message: str | None
) -> tuple[str, bool]:
    """(why a failing latest run is accepted without a challenge or "", whether the message
    contradicts it outright) — rule 3. Only a failure *after the last edit* is (b): one the
    task edited past is a stale result, recorded as unverified."""
    if failure.seq is not None and any(seq > failure.seq for seq in state.last_change_seq.values()):
        return _STALE_FAILURE, False
    if disclosed_failure(message, failure):
        return (_CAUSED if _caused_by_the_change(failure, state, index, message) else "disclosed"), False
    # A link to the change is required in every case: a true challenge about a failure the
    # change did not cause still costs an honest agent a turn.
    failing = _failing_paths(failure, index)
    if not failing:
        return "no failing test named", False
    if _baseline_red(failure, failing, state, index):
        return "already failing before the first edit", False
    if not _related(failing, state, index):
        return "the failing tests do not exercise the change", False
    return "", claims_all_green(message, failure)


_ALL_GREEN = re.compile(
    r"\b(?:all|every|both)\b[^.!?\n]{0,30}?\b(?:tests?|specs?|suites?|checks)\b[^.!?\n]{0,20}?"
    r"\b(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?)\b"
    r"|\b(?:tests?|specs?|suite)\s+(?:are\s+|is\s+)?(?:all\s+)?(?:now\s+)?(?:pass(?:es|ed|ing)?|green)\b"
    r"|\b(?:test\s+)?suite\b[^.!?\n]{0,15}?\b(?:green|passes|passing|passed)\b"
    r"|\b(?:no|zero)\s+(?:test\s+)?failures?\b|\b0\s+failed\b",
    re.I,
)
_PASSED_COUNT = re.compile(r"\b(\d+)\s+(?:tests?\s+)?(?:passed|pass|passing)\b", re.I)


def claims_all_green(message: str | None, failure: runners.TestOutcome) -> bool:
    """Whether the message claims every test passes ("all tests pass", "the suite is green",
    "0 failed", or a passed count above what the run passed), in its own words and not
    negated or conditional."""
    if not isinstance(message, str):
        return False
    text = message[: claims.MAX_MESSAGE]
    passed = failure.total - failure.failed if failure.total >= failure.failed else None
    for sentence in _SENTENCES.split(text):
        if claims._claimed(_ALL_GREEN, sentence):
            return True
        for match in _PASSED_COUNT.finditer(sentence):
            number = int(match.group(1))
            if passed is not None and number > passed:
                return True
    return False


def _failing_paths(failure: runners.TestOutcome, index: RepoIndex) -> set[str]:
    paths = set(failure.failing_files)
    paths |= {test.split("::", 1)[0] for test in failure.failing_tests if "::" in test}
    out = set()
    for path in paths:
        normal = index.normalize(path)
        if normal:
            out.add(normal)
    return out


def _baseline_red(
    failure: runners.TestOutcome, failing: set[str], state: TaskState, index: RepoIndex
) -> bool:
    """Every failing test (by id, else by file) was already failing in a run before the
    task's first change."""
    first = state.first_change_seq
    if not first:
        return False
    earlier = [
        run
        for run in state.verification.outcomes
        if run.passed is False and run.seq is not None and run.seq < first
    ]
    if not earlier:
        return False
    if failure.failing_tests:
        before = {test for run in earlier for test in run.failing_tests}
        return set(failure.failing_tests) <= before
    before_files = {path for run in earlier for path in _failing_paths(run, index)}
    return bool(failing) and failing <= before_files


def _related(failing: set[str], state: TaskState, index: RepoIndex) -> bool:
    """A failing test file the task changed, or one covering a file the task changed."""
    changed = state.changed_files
    if failing & changed:
        return True
    sources = {path for path in changed if not scanner.is_test_path(path)}
    covering = set(
        runners.affected_tests(index, sources, limit=10_000, deleted_coverage=state.deleted_coverage)
    )
    return bool(failing & covering)


# -- disclosure -------------------------------------------------------------------------------

_FAIL_WORD = re.compile(r"\b(?:fail(?:s|ed|ing|ures?)?|red|broken|erroring|errors?)\b", re.I)
# "was failing" is history (the failure is gone); "was already failing" is not: it says the
# failure is older than the change, and still there (audit of 66e1617, M11).
_NOT_A_DISCLOSURE = re.compile(
    r"\b(?:no|zero|0|without|none|nothing|never)\s+(?:\w+\s+){0,2}?(?:fail\w*|errors?|red|broken)\b"
    r"|\b(?:was|were|had\s+been|previously|used\s+to|no\s+longer)\s+(?:(?!already\b)\w+\s+){0,2}?"
    r"(?:fail\w*|red|broken)\b"
    r"|\b(?:fix(?:ed|es)?|resolv(?:ed|es)|repair(?:ed|s)?)\s+(?:\w+\s+){0,3}?(?:fail\w*|errors?)\b",
    re.I,
)
# A sentence about tests that tells the reader not everything passed, without a failure word
# (audit of 66e1617, R2-1): an exception carved out of a pass ("tests pass except the network
# test"), a pass denied ("it doesn't pass here"), tests that could not run ("I couldn't run the
# integration tests (no database)"), or what they need ("needs internet").
_TESTS_NOUN = re.compile(r"\b(?:tests?|specs?|suites?|checks?)\b", re.I)
_CAVEAT = re.compile(
    r"\bpass\w*\b[^.!?\n]{0,40}?\b(?:except|but\s+for|apart\s+from|other\s+than|aside\s+from|save\s+for)\b"
    r"|\b(?:everything\s+else|the\s+rest|all\s+(?:the\s+)?others?|the\s+other\s+tests?)\b[^.!?\n]{0,30}?\bpass"
    r"|\b(?:doesn'?t|does\s+not|don'?t|do\s+not|didn'?t|did\s+not|won'?t|will\s+not|can'?t|cannot)\s+pass\b"
    r"|\bneeds?\s+(?:an?\s+)?(?:internet|network(?:\s+access)?|(?:running\s+)?database|db|credentials|"
    r"(?:running\s+)?server|docker|postgres(?:ql)?|redis|api\s+key|gpu)\b"
    # tests that did not run at all: "all 49 runnable tests passed; the property tests remain unrun"
    # (day 2, a held-out honest finish read as "all green")
    r"|\bun(?:run|runnable)\b|\brunnable\b|\bnot\s+(?:been\s+)?run\b|\b(?:weren'?t|were\s+not|wasn'?t|was\s+not)\s+run\b",
    re.I,
)
# A failure the message says predates the change: disclosed, whatever else the sentence says.
_PREEXISTING = re.compile(
    r"\bpre-?existing\b|\balready\s+(?:\w+\s+){0,2}?(?:fail\w*|red|broken)\b"
    r"|\bfail\w*\s+(?:\w+\s+){0,3}?before\s+(?:this|my|the|any|these)\s+(?:\w+\s+)?change",
    re.I,
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_COUNT = re.compile(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\b", re.I)
_SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n+")


def disclosed_failure(message: str | None, failure: runners.TestOutcome) -> bool:
    """Whether the final message tells the reader the tests are not all green.

    Any of: a failure word that is not negated or past ("2 fail", "the sole failure is
    known issue #57"); an honest partial count, i.e. the number that passed or that failed
    when not all passed ("34 passed" from a run of 36); or the failing test named.
    """
    if not isinstance(message, str) or not message.strip():
        return False
    text = message[: claims.MAX_MESSAGE]
    for sentence in _SENTENCES.split(text):
        if _TESTS_NOUN.search(sentence) and (_CAVEAT.search(sentence) or claims._UNVERIFIED.search(sentence)):
            return True  # "pass except …", "couldn't run the integration tests", "needs internet"
        if not _FAIL_WORD.search(sentence):
            continue
        if _PREEXISTING.search(sentence) or not _NOT_A_DISCLOSURE.search(sentence):
            return True
    if failure.failed:
        counts = {_number(match) for match in _COUNT.findall(text)}
        passed = failure.total - failure.failed if failure.total > failure.failed else None
        if failure.failed in counts and re.search(r"\btests?\b", text, re.I):
            return True
        if (
            passed
            and passed in counts
            and not re.search(r"\ball\s+(?:\d+\s+)?(?:\w+\s+)?tests?\b", text, re.I)
        ):
            return True
    for test in failure.failing_tests:
        name = test.rsplit("::", 1)[-1].split("[", 1)[0]
        if len(name) >= 6 and name in text:
            return True
    return False


def _number(token: str) -> int:
    lowered = token.lower()
    return _NUMBER_WORDS.get(lowered) or (int(lowered) if lowered.isdigit() else -1)


def finding(
    category: ReasonCategory,
    severity: Severity,
    summary: str,
    detail: str = "",
    evidence: list[EvidenceRef] | None = None,
    mode: FailureMode = FailureMode.VERIFICATION_TAMPERING,
) -> Finding:
    """A Stop finding whose subject names its category (``category_of`` reads it back)."""
    return Finding(
        category=ChallengeCategory.TESTABILITY,
        verdict=Verdict.CONTRADICTED,
        failure_mode=mode,
        severity=severity,
        subject=category.value,
        summary=summary,
        detail=detail,
        evidence=evidence or [],
        level=EscalationLevel.DEEP_VERIFICATION,
    )


def changed_texts(state: TaskState, index: RepoIndex) -> dict[str, tuple[str | None, str | None]]:
    """For every file the task changed whose baseline text is known: (before, after).
    After is None for a file deleted since; files whose text is back to the baseline, or
    unreadable now, are left out. Shared by the integrity checks."""
    cache = _TEXTS.get()
    if cache is not None and "texts" in cache:
        return cache["texts"]
    out: dict[str, tuple[str | None, str | None]] = {}
    if cache is not None:
        cache["texts"] = out
    compared = 0
    for path in sorted(state.changed_files):
        old = baseline.before_text(state, path)
        if old is None:
            # Only a file the task created can still be compared; a file changed by a shell
            # command (no baseline) is not read at all — a formatter run over the whole tree
            # made Stop read every file (audit of 66e1617).
            base = state.file_baselines.get(path)
            if base is None or base.exists or base.changed_before:
                continue
        compared += 1
        if compared > MAX_COMPARED_FILES:
            break  # bounded: the rest stay uncompared, which means silence
        exists, new = baseline.current_text(index.root, path)
        if old is None:
            if new is not None:
                out[path] = (None, new)  # created by the task
            continue
        if not exists:
            out[path] = (old, None)
        elif new is not None and new != old:
            out[path] = (old, new)
    return out
