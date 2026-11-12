"""Spec erosion without test pressure: a request that relies on the rule it rewrote (day 7).

Spec erosion (``verify/spec_snapshot.py``) speaks only under test pressure: a request about failing
tests, or a test that failed before the change. Without it, a documented rule removed or qualified
is recorded only, because a behaviour change the user asks for legitimately rewrites the docs that
described the old behaviour.

One more thing tells an impossible request apart from that: **the request relies on the documented
rule**. A sentence of the request states a constraint (must, has to, keep, stay, still, ...) and points
at the project's documentation as its authority: "named the way the README documents", "as the
README says", "README-documented", "every variable in docs/ops.md keeps working as today". The change
then removed or qualified a rule of that very document, and the rule is about what that sentence is
about (at least two content words in common). The request asked for the documented behaviour;
rewriting the documentation instead does not meet it, whatever the tests say. That erosion speaks.

Everything else stays as it was: the rule must be one the request did not ask to change (a doc or
rule change it asked for exempts it, as for every erosion), the change must have touched production
code, and the concern speaks only on a completion claim. A sentence that cites the docs as a style
to follow ("add X, as the docs describe for Y": no constraint), a document other than the one cited,
or a rule about something else (the request relies on the README's output format, the change moved
its timeout) binds nothing. Pure text work at Stop: nothing new on the per-tool-call path, nothing run.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

__all__ = ["FINISH", "Binding", "binds", "bound_docs"]

# No test pressed for the change, so the hand-back names the requirement, not a test.
FINISH = (
    "Accepted finish: restore the rule and the behaviour it documents, then finish with "
    '"not done: <which requirement contradicts which documented rule>", so the user decides.'
)

_DOC = (
    r"(?:readme(?:\.[a-z]+)?|docs?|documentation|runbook(?:s)?|changelog|manual|guide|"
    r"[\w./-]+\.(?:md|markdown|rst|adoc|txt))"
)
_SAYS = (
    r"(?:says?|said|describes?|described|documents?|documented|specifies|specified|states?|stated|"
    r"promises?|lists?|defines?|spells?\s+out)"
)
_ANCHOR = re.compile(
    # as / like / the way / what  the README says
    rf"\b(?:as|like|the\s+way|how|what)\s+(?:the\s+|our\s+|its\s+|their\s+)?(?P<a>{_DOC})(?:'s)?\s+"
    rf"(?:already\s+|currently\s+)?{_SAYS}\b"
    # README-documented, documented in the README, as documented
    rf"|\b(?P<b>{_DOC})-documented\b"
    rf"|\bdocumented\s+(?:in|by)\s+(?:the\s+|our\s+)?(?P<c>{_DOC})\b"
    r"|\bas\s+documented\b"
    # keep ... in <doc> ... as today; in <doc> ... keeps working
    rf"|\b(?:keep|stay|remain|still)\w*\b[^.!?\n]{{0,80}}?\b(?:in|from)\s+(?P<d>{_DOC})\b[^.!?\n]{{0,80}}?"
    r"\b(?:as\s+(?:it\s+does\s+)?today|like\s+today|as\s+(?:it\s+)?(?:does|did|is)\s+(?:now|today)|as\s+before|"
    r"unchanged|working)\b"
    rf"|\b(?:in|from)\s+(?P<e>{_DOC})\b[^.!?\n]{{0,80}}?\b(?:keeps?|stays?|remains?)\s+(?:working|unchanged|"
    r"the\s+same|as\s+(?:it\s+(?:does|is)\s+)?today|like\s+today)\b",
    re.IGNORECASE,
)
# The sentence states a constraint the change must meet, not a style to follow ("add X, as the
# docs describe for Y" binds nothing).
_CONSTRAINT = re.compile(
    r"\b(?:must|has\s+to|have\s+to|needs?\s+to|need|keep\w*|stay(?:s|ing)?|still|remains?|"
    r"can'?t|cannot|never|always|exactly|unchanged|as\s+today|like\s+today)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?;])\s+(?=[A-Za-z(`\"'])|\n{2,}")
# Words of the anchor itself, never evidence that the sentence and the rule share a subject.
_ANCHOR_WORDS = frozenset(
    {
        "readme", "docs", "documentation", "documented", "documents", "document", "runbook",
        "changelog", "manual", "guide", "says", "said", "describes", "described", "specifies", "specified",
        "states", "stated", "promises", "lists", "defines", "spells", "must", "keep", "keeps", "kept", "stay",
        "stays", "still", "remain", "remains", "need", "needs", "today", "exactly", "unchanged", "working",
        "always", "never", "cannot",
    }
)  # fmt: skip
_SUBJECT_WORD = re.compile(r"[a-z][a-z0-9_]{3,}")
MIN_SHARED = 2


class Binding:
    """The documents a request relies on, each with the words of the sentences that cite it."""

    __slots__ = ("docs",)

    def __init__(self) -> None:
        self.docs: dict[str, set[str]] = {}

    def __bool__(self) -> bool:
        return bool(self.docs)


def _words(text: str) -> set[str]:
    """Content words (4+ characters), the anchor's own vocabulary (and its plurals) left out."""
    words = _SUBJECT_WORD.findall(text.lower())
    return {w for w in words if w not in _ANCHOR_WORDS and w[:-1] not in _ANCHOR_WORDS}


def bound_docs(prompt: str | None) -> Binding:
    """The documents the request binds its change to (``readme``, a doc path it names such as
    ``docs/ops.md``, or ``*`` for the docs in general), each with the words of its constraint
    sentences. Empty when it binds none."""
    from truthstone.validate.keep_reading import straight_quotes

    text = straight_quotes((prompt or "")[:20_000])
    out = Binding()
    for sentence in _SENTENCE.split(text):
        if not _CONSTRAINT.search(sentence):
            continue
        for match in _ANCHOR.finditer(sentence):
            doc = next((group for group in match.groups() if group), None)
            name = (doc or "").lower().strip("./")
            if not name:
                key = "*"
            elif name.startswith("readme"):
                key = "readme"
            elif "/" in name or "." in name:
                key = name
            else:
                key = "*"
            out.docs.setdefault(key, set()).update(_words(sentence))
    return out


def _same_stem(word: str, other: str) -> bool:
    """One word, an inflection of the other, or the same first five letters."""
    if word == other:
        return True
    short, long_ = sorted((word, other), key=len)
    if long_.startswith(short) and len(long_) - len(short) <= 3:
        return True
    return len(word) >= 5 and len(other) >= 5 and word[:5] == other[:5]


def binds(binding: Binding, path: str, rule: str) -> bool:
    """Whether the request relies on the rule ``rule`` of the document ``path``: it cites that
    document (or the docs in general) in a constraint sentence that shares at least ``MIN_SHARED``
    content words with the rule."""
    from truthstone.validate import spec_integrity

    if not binding or not spec_integrity.is_doc_path(path):
        return False
    lower = path.lower().lstrip("./")
    name = PurePosixPath(lower).name
    rule_words = _words(rule)
    for doc, words in binding.docs.items():
        cited = (
            doc == "*"
            or (doc == "readme" and name.startswith("readme"))
            or lower == doc
            or lower.endswith("/" + doc)
            or ("/" not in doc and name == doc)
        )
        if not cited:
            continue
        shared = {w for w in words if any(_same_stem(w, r) for r in rule_words)}
        if len(shared) >= MIN_SHARED:
            return True
    return False
