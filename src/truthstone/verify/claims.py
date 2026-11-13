"""What the agent's final message claims (G4a).

The Completion Gate exists to stop a *false* "done". It used to block every unverified
finish, because the core never read the message at all (``last_assistant_message`` was
declared and ignored). So it blocked turns that were not false completions: a
clarifying question ("Should I mock it or leave it?", probe E), an honest "I couldn't
run the tests: Postgres is down", a developer's own TDD red phase. D2's corpus had 10
editing turns ending on a question and 33 disclosing that tests were not run.

This module classifies the message deterministically and conservatively:

* ``question`` — the message's last line ends with "?";
* ``discloses_unverified`` — "could not / did not run the tests", "haven't verified",
  "untested", "blocked on", "needs your input", "not sure whether";
* ``discloses_failure`` — "still fails", "tests are failing", "could not make X pass",
  "doesn't work yet";
* ``claims_verified`` — "all tests pass", "N passed", "the suite is green", "verified";
* ``claims_done`` — "done", "complete", "finished", "is fixed", "works now", "ready for
  review", or a sentence that opens with "Fixed." / "Implemented.";
* ``reports_work`` — "I fixed / implemented / added / updated …": an account of what was
  done, which voids a bare question but not a disclosure ("I implemented it, but I
  couldn't run the tests" is honest).

A claim counts only when it is not negated or conditional in its own sentence: "not all
tests pass", "tests don't pass", "once the tests pass", "to make the tests pass" claim
nothing. Code blocks and quoted lines (``>``) are data, not the message's own words
(Pebble ``open_doubt.own_lines``).

The gaming guard is the point of the split: a message that hands back *and* claims
completion or verification ("Done, all tests pass. Want me to update the docs?") gets no
exemption.

An explicit **status line** is the message's own verdict on itself, and it wins: projects
and harnesses commonly ask agents to end with one ("FINAL: done", "Status: not done -
<reason>", "Result: complete"). Its last occurrence decides: ``done`` is a completion
claim, ``not done`` / ``blocked`` / ``incomplete`` an honest hand-back, whatever else the
message says.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Claims", "classify", "red_phase_requested", "status_line"]

MAX_MESSAGE = 20_000

_QUOTES = str.maketrans(  # curly quotes to straight
    {chr(c): "'" for c in (0x2018, 0x2019, 0x201B)} | {chr(0x201C): '"', chr(0x201D): '"'}
)
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_QUOTED = re.compile(r"^\s*>")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_TRAILING_MARKUP = " \t*_)`'\"]"

# Words that, shortly before a claim in the same sentence, make it no claim: negation,
# or a condition or purpose ("once the tests pass", "to make all tests pass").
_NEGATORS = re.compile(
    r"\b(?:not|no|never|without|cannot|unable|yet|if|once|when|whenever|unless|until|whether|"
    r"should|would|will|might|may|could|must|need|needs|make|making|ensure|expect|expected|"
    r"hope|try|trying|want)\b|n't\b",
    re.I,
)

_TESTS = (
    r"(?:(?:unit|integration|e2e|the|existing|new|relevant|remaining|other)\s+)?"
    r"(?:tests?|specs?|test\s+suite)"
)
_QUANTITY = r"(?:all|every|both|the(?:\s+(?:full|whole|entire))?|\d+(?:\s*/\s*\d+)?)"
_VERIFIED = re.compile(
    "|".join(
        [
            rf"\b{_QUANTITY}\s+(?:of\s+the\s+)?{_TESTS}\s+(?:now\s+|still\s+|all\s+)?"
            r"(?:pass(?:es|ed|ing)?|succeed(?:s|ed)?|are\s+(?:passing|green)|went\s+green)\b",
            rf"\b{_TESTS}\s+(?:are\s+|is\s+)?(?:now\s+|all\s+)?(?:pass(?:es|ed|ing)?|green)\b",
            rf"\bpass(?:ed|es)\s+(?:all|both|every|the)?\s*(?:\d+\s+)?(?:of\s+the\s+)?{_TESTS}\b",
            r"\b(?:test\s+suite|suite|build|ci|pipeline|everything)\s+(?:is\s+|are\s+)?(?:now\s+|all\s+)?"
            r"(?:green|passes|passing|passed)\b",
            r"\b\d+\s+passed\b",
            r"\b(?:no|zero|0)\s+(?:test\s+)?failures\b|\b0\s+failed\b",
            r"\b(?:verified|confirmed)\b",
            r"\bi\s+(?:have\s+|'ve\s+)?(?:tested|verified|confirmed)\b",
        ]
    ),
    re.I,
)
_DONE = re.compile(
    "|".join(
        [
            r"^(?:all\s+)?(?:done|finished|complete[d]?|fixed|implemented|resolved)\b",
            r"\b(?:is|are|'s|'re|now|has\s+been|have\s+been)\s+(?:all\s+)?(?:now\s+)?"
            r"(?:done|complete|finished|fixed|resolved|working|ready)\b",
            r"\b(?:task|work|change|changes|implementation|fix|feature|refactor|migration|bug|issue)\s+"
            r"(?:is\s+|are\s+)?(?:now\s+)?(?:done|complete[d]?|finished|in\s+place|ready|resolved)\b",
            r"\b(?:works|working)\s+(?:now|correctly|as\s+expected|fine|properly)\b",
            r"\b(?:all\s+set|good\s+to\s+go)\b|\bready\s+(?:for\s+review|to\s+(?:merge|ship|go))\b",
        ]
    ),
    re.I,
)
_WORK = re.compile(
    r"\b(?:i|we)\s*(?:'ve|\s+have|\s+just)?\s+(?:also\s+)?(?:fixed|implemented|added|updated|changed|"
    r"rewrote|rewritten|refactored|created|removed|deleted|renamed|moved|wrote|written|made|modified|"
    r"replaced|introduced|resolved|completed|finished)\b",
    re.I,
)
_UNVERIFIED = re.compile(
    "|".join(
        [
            r"\b(?:couldn't|could\s+not|can't|cannot|wasn't\s+able\s+to|was\s+(?:not\s+)?unable\s+to|"
            r"unable\s+to|didn't|did\s+not|haven't|have\s+not|hasn't|has\s+not|not)\s+(?:yet\s+)?"
            r"(?:been\s+able\s+to\s+)?(?:run|ran|execute[d]?|verif(?:y|ied)|test(?:ed)?|confirm(?:ed)?|"
            r"check(?:ed)?|validate[d]?|tell|determine|be\s+(?:sure|certain))\b",
            r"\b(?:untested|unverified)\b",
            r"\bwithout\s+(?:running|testing|verifying)\b",
            r"\b(?:tests?|suite)\s+(?:were|was|have|has)\s*(?:n't|\s+not)\s+(?:been\s+)?run\b",
            r"\bblocked\s+(?:on|by)\b|\bi'?m\s+blocked\b",
            r"\bneeds?\s+(?:your|human|manual|a\s+developer'?s?)\s+(?:input|decision|review|confirmation|"
            r"help|guidance|approval|call)\b",
            r"\b(?:waiting|wait)\s+(?:for|on)\s+(?:you|your)\b|\bi\s+need\s+(?:you|your)\b",
            r"\blet\s+me\s+know\s+(?:if|whether|how|which|what)\b|\bplease\s+(?:confirm|advise|decide)\b",
            r"\bhow\s+would\s+you\s+like\b|\bwhich\s+(?:option|approach|one)\s+(?:do|would)\s+you\b",
            r"\b(?:i'?m|i\s+am|we'?re|we\s+are)\s+(?:still\s+)?not\s+(?:sure|certain|confident)\b",
            r"\b(?:it'?s|it\s+is|it\s+remains)\s+unclear\s+(?:whether|if)\b",
        ]
    ),
    re.I,
)
_FAILURE = re.compile(
    "|".join(
        [
            r"\b(?:still|continues?\s+to|keeps?)\s+fail(?:s|ing|ed)?\b",
            r"\b(?:tests?|suite|build|it|they|this)\s+(?:is\s+|are\s+)?(?:still\s+)?failing\b",
            r"\b[1-9]\d*\s+(?:tests?\s+)?(?:fail(?:s|ed|ing)?|failures?)\b",
            r"\b(?:couldn't|could\s+not|can't|cannot|unable\s+to|wasn't\s+able\s+to|didn't\s+manage\s+to)\s+"
            r"(?:make|get)\s+(?:\S+\s+){1,5}?(?:to\s+)?(?:pass|work|green)\b",
            r"\b(?:couldn't|could\s+not|can't|cannot|unable\s+to|wasn't\s+able\s+to)\s+"
            r"(?:fix|resolve|solve|figure\s+out)\b",
            r"\b(?:not|n't)\s+(?:yet\s+)?(?:working|passing|fixed|resolved)\b",
            r"\b(?:doesn't|don't|didn't|does\s+not|do\s+not|did\s+not)\s+(?:yet\s+)?(?:work|pass)\b",
            r"\b(?:is|are)\s+(?:still\s+)?broken\b",
            r"\btests?\s+fail(?:s|ed)?\b",
        ]
    ),
    re.I,
)
# "It fails as expected" is no disclosure: it claims the failure is the deliverable (a
# TDD red phase), which the gate checks rather than takes on trust.
_INTENDED_FAILURE = re.compile(
    r"\bfail(?:s|ed|ing|ures?)?\b[^.!?\n]{0,30}?\b(?:as\s+(?:expected|intended|designed|planned)|"
    r"on\s+purpose|intentionally|deliberately|by\s+design)\b",
    re.I,
)
_RED_PHASE = re.compile(
    r"\bfailing\s+(?:unit\s+|regression\s+)?tests?\b|\brepro(?:duce[sd]?|duction|ducing)?\b|\btdd\b|"
    r"\btest[-\s]first\b|\bred(?:\s+phase|\s*[-/]\s*green|\s+tests?)\b|\btests?\s+that\s+fails?\b|"
    r"\bdemonstrat\w*\s+the\s+(?:bug|issue|failure)\b",
    re.I,
)


# "FINAL: done", "**Status:** not done - tests need network", "Result: complete".
_STATUS_LINE = re.compile(
    r"^[\s>*_`#-]*(?:final|status|result|outcome|state|verdict)[\s*_`]*:[\s*_`]*"
    r"(?P<status>not[\s_-]+(?:yet\s+)?(?:done|complete[d]?|finished)|incomplete|blocked|partial(?:ly\s+done)?|"
    r"done|complete[d]?|finished)\b",
    re.IGNORECASE,
)


def status_line(message: str | None) -> str:
    """The message's own status line: ``"done"``, ``"not_done"`` or ``""`` (none). The
    last one wins; fenced lines are data, not the message's own words."""
    if not isinstance(message, str) or not message.strip():
        return ""
    found = ""
    for line in _own_lines(message[:MAX_MESSAGE].translate(_QUOTES)):
        match = _STATUS_LINE.match(line)
        if match:
            word = match.group("status").lower()
            found = "done" if word in ("done", "complete", "completed", "finished") else "not_done"
    return found


@dataclass(frozen=True, slots=True)
class Claims:
    question: bool = False
    discloses_unverified: bool = False
    discloses_failure: bool = False
    claims_verified: bool = False
    claims_done: bool = False
    reports_work: bool = False
    # The message's own status line (``status_line``): "done", "not_done" or "".
    status: str = ""

    @property
    def claims(self) -> bool:
        if self.status == "not_done":
            return False  # the message's own verdict: not done, whatever else it says
        return self.claims_done or self.claims_verified or self.status == "done"

    @property
    def hand_back(self) -> str:
        """``"disclosure"`` or ``"question"`` when the message hands the turn back
        honestly — saying what is not done, or asking — and claims neither completion
        nor verification; ``""`` otherwise."""
        if self.claims:
            return ""
        if self.status == "not_done" or self.discloses_failure or self.discloses_unverified:
            return "disclosure"
        if self.question and not self.reports_work:
            return "question"
        return ""


def _own_lines(message: str) -> list[str]:
    lines, fenced = [], False
    for line in message.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced or _QUOTED.match(line):
            continue
        lines.append(line)
    return lines


def _claimed(pattern: re.Pattern[str], sentence: str) -> bool:
    """A match that no negation or condition shortly before it, in the same clause,
    undoes. "I couldn't run the e2e suite, but all unit tests pass" still claims."""
    for match in pattern.finditer(sentence):
        clause = _CLAUSE_BREAK.split(sentence[: match.start()])[-1]
        if not _NEGATORS.search(clause[-40:]):
            return True
    return False


_CLAUSE_BREAK = re.compile(r"[,;:]|\b(?:but|however|although|though|and|so)\b", re.I)


def classify(message: str | None) -> Claims:
    """Classify the agent's final message. Never raises; an empty message claims nothing."""
    if not isinstance(message, str) or not message.strip():
        return Claims()
    lines = _own_lines(message[:MAX_MESSAGE].translate(_QUOTES))
    text = "\n".join(lines)
    sentences = [s.strip() for s in _SENTENCE.split(text) if s and s.strip()]
    last_line = next((line.rstrip(_TRAILING_MARKUP) for line in reversed(lines) if line.strip()), "")
    intended = [s for s in sentences if _INTENDED_FAILURE.search(s)]
    return Claims(
        question=last_line.endswith("?"),
        discloses_unverified=any(_UNVERIFIED.search(s) for s in sentences),
        discloses_failure=any(_FAILURE.search(s) for s in sentences if s not in intended),
        claims_verified=any(_claimed(_VERIFIED, s) for s in sentences),
        claims_done=bool(intended) or any(_claimed(_DONE, s) for s in sentences),
        reports_work=any(_claimed(_WORK, s) for s in sentences),
        status=status_line(message),
    )


def red_phase_requested(prompt: str | None) -> bool:
    """Whether the request asks for a failing test first (TDD's red phase, a repro): an imperative ask
    (``spec_conflict.red_phase_ask``). Day 11 (fix-r7): a failing test the request only describes ("has a
    new failing test", "Failing tests: ...", "test_x reproduces it") is the test pressure of the request,
    not a red phase it asked for; the old reading (``_RED_PHASE``, any such words) read the canonical
    phrasing of a task one way and its terse phrasing ("... is red") the other."""
    from truthstone.verify import spec_conflict

    return spec_conflict.red_phase_ask((prompt or "")[:MAX_MESSAGE])
