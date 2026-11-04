"""The completion arbiter (v0.2 M1): one decision per Stop, from claims and evidence.

Every Stop-time check reports here, and the agent hears at most **one** combined challenge
per Stop. The checks are:

* the Completion Gate's evidence (``completion_gate``): failing, stale, narrower or missing
  test runs, unparsable files;
* spec and doc integrity (M2, ``validate/spec_integrity.py``): a documented rule removed or
  qualified;
* test integrity (M4, ``validate/weakened_tests.py``): existing tests weakened, deleted or
  skipped;
* unread configuration (``validate/config_reads.py``): the change only adds configuration
  that nothing in the repository reads.

Each reason has a ``ReasonCategory``, and a category speaks at most once per task.

The rules, in order
-------------------
1. **No completion claim, no challenge.** A question, "not done: <reason>", or a message
   that says what is unverified or failing hands the turn back honestly. It is accepted,
   and the developer is told any gap.
2. **The profile decides who may speak.** ``"minimal"`` (the product default) lets only
   the categories in ``MINIMAL_STOP_CATEGORIES`` reach the agent: a weakened yardstick (a),
   relevant failing tests left undisclosed (b), configuration nothing reads (e).
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
5. **Budget.** At most ``max_blocks`` Stop challenges per task, and none while a stop hook
   already holds the turn. After that the turn ends with the gap reported to the
   developer. It is never held indefinitely.

Never raises; a check that fails is skipped (fail open).
"""

from __future__ import annotations

import contextvars
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

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
from truthstone.verify import baseline, claims, completion_gate, runners

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
    ReasonCategory.TEST_WEAKENING,
    ReasonCategory.TEST_FITTING,
    ReasonCategory.FAILING_TESTS,
    ReasonCategory.UNREAD_CONFIG,
    ReasonCategory.UNPARSABLE,
    ReasonCategory.UNVERIFIED,
)
_SPEAKING = (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


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


def _integrity_checks() -> list[IntegrityCheck]:
    from truthstone.validate import config_reads, weakened_tests
    from truthstone.verify import integrity

    return [integrity.spec_concerns, weakened_tests.concerns, config_reads.concerns]


def arbitrate(
    state: TaskState | None,
    index: RepoIndex,
    message: str | None = None,
    stop_hook_active: bool = False,
    max_blocks: int = 2,
    pending_tasks: list[dict] | None = None,
    profile: str = "minimal",
    checks: Iterable[IntegrityCheck] | None = None,
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

    token = _TEXTS.set({})
    try:
        found_all = []
        for check in checks if checks is not None else _integrity_checks():
            try:
                found_all.append(check(state, index))
            except Exception:
                log.exception("truthstone: a completion integrity check failed; skipped")
    finally:
        _TEXTS.reset(token)
    for found in found_all:
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
            if (
                minimal
                and concern.category is ReasonCategory.SPEC_EROSION
                and SPEC_EROSION_AGAIN not in already
                and again is None
            ):
                # The one exception to once per reason: "done" claimed again over a rewritten
                # documented rule. The second ask is the smallest one: keep the change if you
                # must, but hand the rule decision back. It can only follow a first challenge.
                again = _asked_again(concern)
                speaking.append(again)
                continue
            repeated.append(concern)
        else:
            speaking.append(concern)

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

    # The asked-again challenge follows the agent's own reply to the first one, so a stop hook
    # is holding the turn by construction; the per-task block budget still bounds it.
    muted = completion_gate._muted_reason(state, stop_hook_active and again is None, max_blocks)
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
    if again is not None:
        raised.append(SPEC_EROSION_AGAIN)  # recorded with the categories: asked twice, never thrice
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
    ReasonCategory.SPEC_EROSION: (
        'Accepted finishes: restore the rule and finish with "not done: <which test contradicts '
        'which documented rule>"; or keep the change and finish with "not done: <the rule I changed>, '
        'please confirm", so the user decides.'
    ),
    ReasonCategory.TEST_WEAKENING: (
        'Accepted finishes: restore the test and fix the code, then finish; or finish with "not done: '
        '<which test was weakened, and why>", so the user decides.'
    ),
    ReasonCategory.UNREAD_CONFIG: (
        'Accepted finishes: finish with "not done: <reason>"; or show in your final message which code '
        "reads it."
    ),
}


SPEC_EROSION_AGAIN = "spec_erosion:again"


def _asked_again(concern: Concern) -> Concern:
    """The second, smallest ask over a documented rule still rewritten at a repeated "done"."""
    refs = [ref for ref in concern.finding.evidence if ref.snippet][:3]
    listing = "\n".join(
        f'  - {ref.path}{f":{ref.line}" if ref.line else ""}: "{ref.snippet}"' for ref in refs
    )
    text = (
        "You finished as done again, but the documented rule is still changed:\n"
        f"{listing}\n"
        "A completion that changes a documented rule needs the user's confirmation, whatever the "
        "tests say, and only the user can give it. Keep your change if you are sure of it, but do "
        "not finish as done."
    )
    return Concern(concern.category, text, concern.finding, needs_claim=True)


def _render(concerns: list[Concern]) -> str:
    """One message: who is speaking, each concern, the finishes that are accepted (those of
    the first concern, in the arbiter's order)."""
    if len(concerns) == 1:
        body = concerns[0].text
    else:
        body = "\n\n".join(f"{n}. {c.text}" for n, c in enumerate(concerns, 1))
    finishes = _FINISHES.get(concerns[0].category, _DEFAULT_FINISHES)
    return (
        "Truthstone (an automated check, not the user) found a problem with finishing now.\n\n"
        f"{body}\n\n{finishes}"
    )


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


def _failure_accepted(
    failure: runners.TestOutcome, state: TaskState, index: RepoIndex, message: str | None
) -> tuple[str, bool]:
    """(why a failing latest run is accepted without a challenge or "", whether the message
    contradicts it outright) — rule 3. Only a failure *after the last edit* is (b): one the
    task edited past is a stale result, recorded as unverified."""
    if failure.seq is not None and any(seq > failure.seq for seq in state.last_change_seq.values()):
        return _STALE_FAILURE, False
    if disclosed_failure(message, failure):
        return "disclosed", False
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
    for path in sorted(state.changed_files):
        old = baseline.before_text(state, path)
        exists, new = baseline.current_text(index.root, path)
        if old is None:
            base = state.file_baselines.get(path)
            if base is not None and not base.exists and not base.changed_before and new is not None:
                out[path] = (None, new)  # created by the task
            continue
        if not exists:
            out[path] = (old, None)
        elif new is not None and new != old:
            out[path] = (old, new)
    return out
