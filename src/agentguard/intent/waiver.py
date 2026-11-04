"""Whether a request tells the agent not to run tests — or asks it to write some (G6).

The waiver used to be a substring list: "no tests" anywhere waived verification. So
"…the module has no tests; fix it and add tests" waived it (probe G), as did "make sure
there are no tests failing" and "shipped without tests; add some", while 11 of 12
paraphrases of a real instruction were missed — "Don't run the tests" written with a
curly apostrophe among them (docs/IMPROVEMENTS.md G6, D2).

A waiver is an *instruction*, so it is read as one: an imperative not to run the tests,
anchored at the start of a clause. Port of Pebble ``backend/pebble/guard.py:70-77``
(``WAIVER``; same owner, Apache-2.0), extended with a few more phrasings and with
clause boundaries at commas, em and en dashes and a spaced hyphen — so the
long-standing "Fix paginate — skip tests." still waives. Quotes are normalised first.

Descriptions are not instructions: "has no tests", "there are no tests", "without
tests", "no tests fail" never waive.

``requests_tests`` is the opposite signal: the developer asked for tests to be written.
It ends a waiver carried over from an earlier prompt, and the gate holds a task that was
asked for tests and wrote none.
"""

from __future__ import annotations

import re

__all__ = ["normalise", "requests_tests", "waives"]

# Curly single quotes, the reversed-9 quote and the prime become "'"; curly doubles '"'.
_QUOTES = str.maketrans(
    {chr(c): "'" for c in (0x2018, 0x2019, 0x201B, 0x2032)} | {chr(0x201C): '"', chr(0x201D): '"'}
)
_DASHES = chr(0x2014) + chr(0x2013)  # em and en dash

# Where an instruction can start: the beginning, a sentence or clause mark, a dash used as
# punctuation, or a joining word.
_CLAUSE = r"(?:^|[.;:!?\n(," + _DASHES + r"]|\s-{1,2}\s|\b(?:and|but|then|so|also|just|please)\b)\s*"
# Words that may precede the imperative itself: "please", "now", "can you", "let's", ...
_POLITE = (
    r"(?:(?:please|pls|just|also|and|now|then|next|finally|first|can\s+you|could\s+you|would\s+you"
    r"|will\s+you|you\s+(?:should|can|may)|we\s+(?:should|need\s+to)|i\s+(?:want|need)\s+you\s+to"
    r"|let'?s),?\s+)*"
)
_DO_NOT = (
    r"(?:do\s+not|don'?t|never|no\s+need\s+to|there'?s\s+no\s+need\s+to|there\s+is\s+no\s+need\s+to"
    r"|(?:you\s+)?(?:do\s+not|don'?t)\s+(?:need|have)\s+to|needn'?t|should\s+not|shouldn'?t|avoid)"
)
_RUN = r"(?:bother\s+(?:to\s+|with\s+)?)?(?:re-?)?(?:run(?:ning)?|execut(?:e|ing)|invok(?:e|ing))"
_THE = r"(?:(?:the|any|all|of\s+the|our|your)\s+)?(?:(?:whole|full|entire|existing|unit|test)\s+)?"
_TESTS = r"(?:tests?|test\s+suite|suite|specs?|pytest|jest|vitest|unit\s+tests?)\b"

WAIVER = re.compile(
    _CLAUSE
    + _POLITE
    + r"(?:"
    + rf"{_DO_NOT}\s+{_RUN}\s+{_THE}{_TESTS}"
    + rf"|skip(?:ping)?\s+(?:running\s+)?{_THE}(?:{_TESTS}|testing\b)"
    + r"|(?:do\s+not|don'?t)\s+(?:bother\s+(?:with\s+)?)?test(?:ing)?\b"
    + r"(?!\s*(?:files?|cases?|data|fixtures?)\b)"
    + r"|(?:do\s+not|don'?t)\s+(?:worry|bother)\s+(?:about|with)\s+(?:the\s+|any\s+)?(?:tests?|testing)\b"
    + r"|no\s+need\s+to\s+(?:re-?)?test\b"
    + r"|no\s+(?:need\s+for\s+)?(?:tests?|testing)(?:\s+(?:needed|necessary|required))?\s*(?=[.!;,)]|$)"
    + r"|(?:tests?|testing)\s+(?:(?:is|are|were)\s*)?"
    + r"(?:(?:not|n'?t)\s+(?:needed|necessary|required)|unnecessary)\b"
    + r"|(?:tests?|testing)\s+can\s+(?:be\s+skipped|wait)\b"
    + r")"
    + r"|\b(?:without|w/o)\s+(?:re-?)?running\s+(?:the\s+|any\s+)?(?:unit\s+)?"
    + r"(?:tests?|test\s+suite|specs?)\b",
    re.I,
)

# An instruction to *write* tests: add/write/create/include tests, cover with tests, TDD.
_WRITE = r"(?:add(?:ing)?|writ(?:e|ing)|creat(?:e|ing)|includ(?:e|ing)|implement(?:ing)?|extend(?:ing)?)"
_SOME = r"(?:(?:a|an|some|more|new|the|missing|proper|unit|regression|integration|failing|e2e|basic)\s+){0,3}"
# "add test ids / test data / test users" is not a request for tests.
_NOT_TESTS = (
    r"(?![-_]|\s+(?:ids?|attributes?|selectors?|data|users?|accounts?|mode|env|environment"
    r"|credentials?|keys?|flags?|servers?|database|db|doubles?|helpers?|utils?)\b)"
)
REQUEST = re.compile(
    _CLAUSE
    + _POLITE
    + r"(?:"
    + rf"{_WRITE}\s+{_SOME}(?:unit\s+)?(?:tests?|test\s+cases?|test\s+coverage|specs?)\b{_NOT_TESTS}"
    + r"|cover\s+(?:it|this|them|that|these|those|the\s+\w+|\w+)\s+with\s+(?:a\s+|unit\s+)?tests?\b"
    + r"|(?:use\s+)?tdd\b|test[-\s]first\b"
    + r")"
    + r"|\b(?:with|plus)\s+(?:unit\s+|regression\s+)?tests?\s*(?=[.!;,)]|$)",
    re.I,
)


def normalise(text: str) -> str:
    """Curly quotes to straight, runs of blanks to one space (newlines are kept: they
    end a clause)."""
    return _BLANKS.sub(" ", (text or "").translate(_QUOTES))


_BLANKS = re.compile(r"[ \t\r\f\v]+")


def waives(prompt: str) -> bool:
    """Whether the request tells the agent not to run the tests."""
    return bool(WAIVER.search(normalise(prompt)[:20_000]))


def requests_tests(prompt: str) -> bool:
    """Whether the request asks the agent to write tests."""
    return bool(REQUEST.search(normalise(prompt)[:20_000]))
