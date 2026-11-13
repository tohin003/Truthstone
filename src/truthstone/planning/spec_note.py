"""The spec note: the documented rule closest to a "make this failing test pass, keep the tests"
request, quoted once per session at prompt time (day 5).

Ported from the design's prototype (``design-t1b.md`` section 2 (i), ``note_proto.py``, ``decide2``).
Under a request that keeps the tests and asks for a red test to pass, a test that contradicts a
documented rule leaves two honest outcomes: say the request cannot be met, or (when the request is
to change the rule) change it in the open. Agents that never looked at the rule take a third one:
change the behaviour and call it done. The Stop checks catch some of the traces that leaves; this
note puts the rule in front of the agent before any work, and forbids nothing.

* **Cheap gate first** (``gate``): the request keeps the tests (``weakened_tests.tests_kept_requested``)
  AND asks for failing tests to pass (``spec_integrity.test_pressure_requested``). Two regex reads of
  the prompt. Almost every session stops here, and then nothing is read.
* **Rule sources** (``units_of``): the blocks of the documentation as the task finds it (README,
  ``docs/**``, change logs; not lists of known issues, plans or TODOs), and the doc comments of
  non-test source files, grouped by owner. A block is normative when it carries the product's markers
  (``spec_integrity.normative_markers`` minus the raises/throws contract marker) or a promise or
  contract word (``_PROMISE``).
* **Request words** (``request_words``): the prompt's content words, ticket ids and the words of how
  a request is framed (``GENERIC``) dropped, identifiers split, crudely stemmed. Added to them: the
  words of the test the request names (``named_tests``: a pytest function, a quoted JS title, or a
  whole named test file of at most ``MAX_TEST_LINES`` lines), at most ``MAX_TEST_LINES`` lines in all.
  Terse prompts name 2-5 content words; the test names the rest.
* **Ranking** (``rank``): idf-weighted overlap over all blocks. The best normative block must share at
  least ``K_MIN`` words, else silence; the next normative block that does is quoted too. Each quote is
  at most ``QUOTE_CHARS`` characters, with ``path:line``.
* **Bounded** (``gather``): the files come from the repository index (no walk), and are chosen by the
  index's sizes before any is read: an index of more than ``MAX_INDEX_FILES`` files, more than
  ``MAX_RULE_FILES`` files or ``MAX_RULE_BYTES`` bytes of rule sources (text docs by suffix, source
  files), or more than ``MAX_TEST_FILES`` / ``MAX_TEST_BYTES`` of test files to search, is silence
  (fail open), logged at INFO; the scan stops at the cap. A single file over ``FILE_BYTES`` is
  skipped. In practice: a small repository gets the note, a large one never does.

Context only: never a hold, a deny or an ask, silent in observe mode, its own kind ``spec_note``
(never a premise flag), at most once per session, and off when ``[notes] spec = false``. A request
that asks to change the rule still gets it: the note's second clause is that case.
"""

from __future__ import annotations

import ast
import logging
import math
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from truthstone.core.enums import ChallengeCategory, FailureMode, Severity, Verdict
from truthstone.core.models import Finding
from truthstone.repo import scanner
from truthstone.validate import spec_integrity as si
from truthstone.validate import weakened_tests

log = logging.getLogger(__name__)

__all__ = ["FINDING_SUBJECT", "Note", "decide", "gate", "render"]

# The subject that names this note's kind for the intervention profile (``core/profile.py``).
FINDING_SUBJECT = "spec_note"

K_MIN = 2  # shared words the best normative block needs
QUOTED = 2  # blocks quoted, at most
QUOTE_CHARS = 300
MAX_TEST_LINES = 150  # lines of the named tests read for words, in all
FILE_BYTES = 256_000  # a larger file is skipped
MAX_RULE_FILES = 100  # rule sources (docs and doc comments); over it, silence
MAX_RULE_BYTES = 256_000
MAX_TEST_FILES = 64  # test files searched for the named test; over it, silence
MAX_TEST_BYTES = 512_000
MAX_INDEX_FILES = 20_000  # a larger repository is not searched at all: silence
_TEST_SUFFIXES = (".py", ".ts", ".js", ".tsx", ".mjs")

LEAD_ONE = (
    "Truthstone (an automated check, not the user): the project documents a rule close to this request:"
)
LEAD_TWO = "Truthstone (an automated check, not the user): the project documents rules close to this request:"
TAIL_ONE = (
    "If the request cannot be met without breaking it, say so instead of changing the behaviour; "
    "if the request is to change that rule, go ahead and update the docs with it."
)
TAIL_TWO = (
    "If the request cannot be met without breaking one of them, say so instead of changing the behaviour; "
    "if the request is to change such a rule, go ahead and update the docs with it."
)


# -- the gate ----------------------------------------------------------------------------------------------


def gate(prompt: str | None, index: Any = None) -> bool:
    """The request keeps the tests and asks for failing tests to pass. Reads the prompt (and, with
    ``index``, resolves the tests it names against the repository: day 11)."""
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    return weakened_tests.tests_kept_requested(prompt) and si.test_pressure_requested(prompt, index)


# -- blocks and words --------------------------------------------------------------------------------------


@dataclass(slots=True)
class Unit:
    path: str
    line: int
    text: str
    kind: str  # doc | code
    words: frozenset[str] = field(default_factory=frozenset)
    normative: bool = False


# A block states a rule: a marker (the product's, minus raises/throws), or a word that names it as a
# promise or a contract.
_PROMISE = re.compile(
    r"\b(?:contract|promise[sd]?|guarantee[sd]?|compatib\w*|rel(?:y|ies|ied)\s+on|depend(?:s|ed)?\s+on|"
    r"invariant|on\s+purpose|by\s+design|part\s+of\s+the\s+(?:api|contract))\b",
    re.IGNORECASE,
)
_LOG_NAMES = re.compile(r"^(?:known[-_ ]?issues|todo|roadmap)(?:\.|$)", re.IGNORECASE)


def _normative(text: str) -> bool:
    return bool(si.normative_markers(text) - si.CONTRACT_MARKERS) or bool(_PROMISE.search(text))


_SOURCE_SUFFIXES = (".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_TEXT_DOC_SUFFIXES = (".md", ".markdown", ".rst", ".adoc", ".txt")


def _rule_source(path: str) -> bool:
    """A file a rule can be read from: a text documentation file (README, ``docs/**``, a change log;
    not a list of known issues, plans or TODOs), or a non-test source file with doc comments. A
    suffix test first, so a large index is filtered cheaply."""
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    if not (lower.endswith(_SOURCE_SUFFIXES + _TEXT_DOC_SUFFIXES) or "." not in name):
        return False
    if si.is_doc_path(path):
        return not _LOG_NAMES.match(PurePosixPath(path).name)
    return si.is_docstring_source(path) and not scanner.is_test_path(path)


def units_of(files: Mapping[str, str]) -> list[Unit]:
    """Every rule-shaped block of ``files`` (path -> text): doc blocks, and doc comments by owner."""
    out: list[Unit] = []
    for path, text in files.items():
        if _LOG_NAMES.match(PurePosixPath(path).name):
            continue
        if si.is_doc_path(path):
            for block, line in si._blocks(text):
                clean = si._MARKUP.sub("", block).strip()
                if len(clean) >= 12:
                    out.append(Unit(path, line, clean, "doc"))
        elif si.is_docstring_source(path) and not scanner.is_test_path(path):
            groups: dict[tuple[str, int], list[str]] = {}
            for sentence in si.doc_sentences(path, text) or []:
                groups.setdefault((sentence.owner, sentence.line), []).append(sentence.text)
            for (_owner, line), texts in groups.items():
                out.append(Unit(path, line, " ".join(texts), "code"))
    for unit in out:
        unit.words = frozenset(_words(unit.text))
        unit.normative = _normative(unit.text)
    return out


_SPLIT_ID = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
# Words of how a request is framed, never of what it is about (generic, not task-specific).
GENERIC = frozenset(
    """
test tests testing spec specs suite suites pass passes passing passed green red fail fails failing
failed failure make makes get gets got touch touching touched change changes changed changing edit
edits edited editing leave alone keep kept new newly added add adding please could would can again
now fix fixes fixed fixing broken break work works working ci qa own owns owned ticket acceptance py
ts js tsx mjs file files line lines npm pytest node run runs running whole thing things want wants
need needs needed let lets go sure ok okay though instead also yet still just really written write
writes check checks checked help hey hi thanks thank today tomorrow afternoon morning release
""".split()  # noqa: SIM905
)
_CONTRACTION = re.compile(r"\b\w+n['\u2019]t\b|['\u2019](?:s|re|ve|ll|d|m)\b|['\u2019]", re.IGNORECASE)
_TICKET = re.compile(r"\b[A-Z]{2,}-\d+\b")


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


_GENERIC_STEMS = frozenset({_stem(g) for g in GENERIC} | GENERIC)


def _words(text: str) -> set[str]:
    text = _CONTRACTION.sub(" ", text)
    text = re.sub(r"(?<=\w)[./:](?=\w)", " ", text)
    words = {w for w in si._content(text) if len(w) > 2 or w.isalpha()}
    for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        if "_" in ident or re.search(r"[a-z][A-Z]", ident):
            for part in _SPLIT_ID.findall(ident):
                words |= set(si._content(part))
    return {_stem(w) for w in words}


def request_words(prompt: str) -> set[str]:
    """The prompt's content words: ticket ids, framing words, numbers and test names dropped."""
    text = _TICKET.sub(" ", prompt)
    return {
        w for w in _words(text) if w not in _GENERIC_STEMS and not w.isdigit() and not w.startswith("test_")
    }


# -- the test the request names ----------------------------------------------------------------------------

_PATHLIKE = re.compile(r"[\w./-]+\.(?:py|ts|tsx|js|mjs|cjs|mts|cts)\b")
_PYTEST = re.compile(r"\btest_\w+")
_TITLE = re.compile(r"[\"\u201c]([^\"\u201d\n]{8,200})[\"\u201d]")
_JS_START = re.compile(r"^\s*(?:test|it|describe)(?:\.\w+)?\s*\(")
_CODE_NOISE = frozenset(
    """
assert assertequal expect equal deepequal strictequal tobe toequal import from const let var
function return def self none true false null undefined new await async raises pytest describe it
test of the
""".split()  # noqa: SIM905
)


@dataclass(frozen=True, slots=True)
class Named:
    """What the request names of its tests: pytest functions, quoted titles, file paths."""

    names: frozenset[str]
    titles: tuple[str, ...]
    paths: frozenset[str]

    def __bool__(self) -> bool:
        return bool(self.names or self.titles or self.paths)


def named(prompt: str) -> Named:
    return Named(
        names=frozenset(_PYTEST.findall(prompt)),
        titles=tuple(m.group(1) for m in _TITLE.finditer(prompt)),
        paths=frozenset(m.group(0).lstrip("./") for m in _PATHLIKE.finditer(prompt)),
    )


def _py_test_body(text: str, name: str) -> str | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node)
    return None


def _js_test_body(text: str, title: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if title in line:
            indent = len(line) - len(line.lstrip())
            out = [line]
            for nxt in lines[i + 1 : i + 60]:
                if _JS_START.match(nxt) and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                out.append(nxt)
            return "\n".join(out)
    return None


def named_tests(prompt: str, tests: Mapping[str, str]) -> list[tuple[str, str]]:
    """(path, body) of each test the request names: a pytest function, a quoted title, or a named
    test file (whole, only when nothing narrower is found and it is short). At most
    ``MAX_TEST_LINES`` lines in all."""
    want = named(prompt)
    out: list[tuple[str, str]] = []
    for path, text in tests.items():
        for name in sorted(want.names):
            body = _py_test_body(text, name) if path.endswith(".py") and name in text else None
            if body:
                out.append((path, body))
        for title in want.titles:
            body = _js_test_body(text, title) if title in text else None
            if body:
                out.append((path, body))
    if not out:
        for path, text in tests.items():
            if any(path.endswith(p) for p in want.paths) and text.count("\n") <= MAX_TEST_LINES:
                out.append((path, text))
    budget, kept = MAX_TEST_LINES, []
    for path, body in out:
        if budget <= 0:
            break
        lines = body.splitlines()[:budget]
        budget -= len(lines)
        kept.append((path, "\n".join(lines)))
    return kept


def words_of_tests(bodies: Iterable[tuple[str, str]]) -> set[str]:
    """The words of the named tests' bodies, and (day 11) of the paths of the files they are in: a
    test named by its bare name reads as the same test named by its node id (``path::name``)."""
    words: set[str] = set()
    for path, body in bodies:
        words |= {w for w in _words(body) if w not in _CODE_NOISE and not w.isdigit()}
        words |= {w for w in request_words(path) if not w.isdigit()}
    return {w for w in words if w not in _GENERIC_STEMS}


# -- the decision ------------------------------------------------------------------------------------------


def rank(words: set[str], units: list[Unit]) -> list[tuple[float, int, Unit]]:
    """(score, shared words, unit), best first: idf-weighted overlap with ``words``."""
    n = len(units) or 1
    df: dict[str, int] = {}
    for unit in units:
        for word in unit.words:
            df[word] = df.get(word, 0) + 1
    scored = []
    for unit in units:
        shared = words & unit.words
        if shared:
            scored.append((sum(math.log(1 + n / df[w]) for w in shared), len(shared), unit))
    scored.sort(key=lambda item: (-item[0], item[2].path, item[2].line))
    return scored


@dataclass(frozen=True, slots=True)
class Note:
    text: str
    quotes: tuple[tuple[str, int, str], ...]  # (path, line, quote)

    def finding(self) -> Finding:
        """The record of the note: what it said, at INFO, never a failure."""
        return Finding(
            category=ChallengeCategory.CONSISTENCY,
            verdict=Verdict.SUPPORTED,
            failure_mode=FailureMode.NOT_A_FAILURE,
            severity=Severity.INFO,
            subject=FINDING_SUBJECT,
            summary="spec note: " + ", ".join(f"{path}:{line}" for path, line, _quote in self.quotes),
            detail=self.text[:1200],
        )


def _quote(text: str) -> str:
    return text if len(text) <= QUOTE_CHARS else text[: QUOTE_CHARS - 3] + "..."


def decide(prompt: str, rules: Mapping[str, str], tests: Mapping[str, str]) -> Note | None:
    """The note for ``prompt`` over these rule sources and test files (path -> text), or None.
    The gate is the caller's (``render``)."""
    units = units_of(rules)
    words = request_words(prompt) | words_of_tests(named_tests(prompt, tests))
    picked: list[Unit] = []
    for _score, shared, unit in rank(words, units):
        if not unit.normative:
            continue
        if shared < K_MIN:
            if not picked:
                return None  # the best normative block is too weak: silence
            continue
        picked.append(unit)
        if len(picked) == QUOTED:
            break
    if not picked:
        return None
    quotes = tuple((u.path, u.line, _quote(u.text)) for u in picked)
    lead, tail = (LEAD_ONE, TAIL_ONE) if len(quotes) == 1 else (LEAD_TWO, TAIL_TWO)
    listing = "\n".join(f'  - {path}:{line}: "{quote}"' for path, line, quote in quotes)
    return Note(f"{lead}\n{listing}\n{tail}", quotes)


# -- reading, bounded ---------------------------------------------------------------------------------------

Reader = Callable[[str], "str | None"]


def gather(
    prompt: str, sizes: Mapping[str, int], read: Reader
) -> tuple[dict[str, str], dict[str, str]] | None:
    """The rule sources and the test files to search, read with ``read`` (path -> text or None),
    chosen by ``sizes`` (path -> bytes, the index's) before anything is read. None over a cap."""
    rules = _within(
        (p for p, size in sizes.items() if size <= FILE_BYTES and _rule_source(p)),
        sizes,
        MAX_RULE_FILES,
        MAX_RULE_BYTES,
        "rule sources",
    )
    if rules is None:
        return None
    want = named(prompt)
    tests: list[str] = []
    if want:
        by_path = not (want.names or want.titles)  # only a file is named: only that file is read
        found = _within(
            (
                p
                for p, size in sizes.items()
                if size <= FILE_BYTES
                and p.endswith(_TEST_SUFFIXES)
                and scanner.is_test_path(p)
                and (not by_path or any(p.endswith(q) for q in want.paths))
            ),
            sizes,
            MAX_TEST_FILES,
            MAX_TEST_BYTES,
            "test files",
        )
        if found is None:
            return None
        tests = found
    rule_texts = {p: t for p in rules if (t := read(p)) is not None}
    test_texts = {p: t for p in tests if (t := read(p)) is not None}
    return rule_texts, test_texts


def _within(
    paths: Iterable[str], sizes: Mapping[str, int], files: int, total: int, what: str
) -> list[str] | None:
    """``paths`` sorted, or None as soon as they pass ``files`` files or ``total`` bytes (the scan
    stops there: a large index costs no more than the cap)."""
    out: list[str] = []
    seen = 0
    for path in paths:
        out.append(path)
        seen += sizes[path]
        if len(out) > files or seen > total:
            log.info(
                "truthstone: spec note skipped: %s over the cap (%d files, %d bytes)", what, files, total
            )
            return None
    return sorted(out)


def reader(root: Any) -> Reader:
    """Reads a repository file the index lists: UTF-8 text inside ``root`` (its real path; one
    ``realpath`` per file), at most ``FILE_BYTES``, not binary; None otherwise."""
    base = os.path.realpath(str(root))

    def read(path: str) -> str | None:
        full = os.path.realpath(os.path.join(base, path))
        if os.path.commonpath([full, base]) != base or not os.path.isfile(full):
            return None
        try:
            with open(full, "rb") as handle:
                data = handle.read(FILE_BYTES + 1)
        except OSError:
            return None
        if len(data) > FILE_BYTES or b"\x00" in data[:8192]:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    return read


def render(prompt: str | None, index: Any) -> Note | None:
    """The note for this prompt in this repository, or None. Gate first: no file is read unless
    the request keeps the tests and asks for failing tests to pass. Never raises."""
    try:
        # The prompt alone first: a request that does not keep the tests touches nothing.
        if not isinstance(prompt, str) or not prompt.strip():
            return None
        if not weakened_tests.tests_kept_requested(prompt):
            return None
        if index is None or not getattr(index, "is_built", False):
            return None
        if not si.test_pressure_requested(prompt, index):
            return None  # day 11: the tests it names, resolved against the repository
        files = dict(index.files)
        if len(files) > MAX_INDEX_FILES:
            log.info("truthstone: spec note skipped: %d indexed files over the cap", len(files))
            return None
        sizes = {path: record.size for path, record in files.items()}
        found = gather(str(prompt), sizes, reader(index.root))
        if found is None:
            return None
        return decide(str(prompt), *found)
    except Exception:  # a note not computed is silence, never a failure
        log.info("truthstone: spec note could not be computed; silent", exc_info=True)
        return None
