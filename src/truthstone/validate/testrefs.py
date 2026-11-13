"""The tests a request names, whatever they look like (day 11).

A request names the test it is about in many ways: a test file (``tests/test_client.py``,
``test/kill-switch.test.ts``), a pytest node id (``tests/test_x.py::test_y``, ``tests/test_x.py -k
test_y``), a bare pytest name (``test_y``), or a quoted JS title ("refunds round half up", in double
or curly quotes or backticks) next to the word "test" or a test file. The older wording readers
(``spec_integrity._PRESSURE``) need a test noun right before "pass", or within 60 characters of
"failing": a path, a node id or a long title between the words broke them, so one phrasing of a
request read as "make this failing test pass" and another phrasing of the same request did not.

``mask`` replaces every test reference with the single word ``testref``; the readers then see "make
testref pass" or "testref is failing" whatever the reference looked like, and a title's own words
("... a disabled flag ...") are no longer read as the request's. With a repository index, a file must
be a test file the index lists, and a quoted span next to no test word still counts when a test file
the request names (else, within ``MAX_FILES`` / ``MAX_BYTES``, any test file) contains it verbatim:
the reference is resolved against the repository, not guessed from the sentence around it.

Standard library and the repository index only. Never raises (``mask`` returns the text unmasked).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from truthstone.repo import scanner

log = logging.getLogger(__name__)

__all__ = ["REF", "Ref", "mask", "refs"]

REF = "testref"
MAX_FILES = 64  # test files read to resolve a quoted title; over it, titles are read from the sentence only
MAX_BYTES = 512_000
FILE_BYTES = 256_000

_CODE_SUFFIX = r"(?:py|pyi|js|jsx|mjs|cjs|ts|tsx|mts|cts)"
# A file path, optionally a pytest node id (``::name`` parts, a parametrisation) or a ``-k`` filter.
_PATH = re.compile(
    rf"(?<![\w@/.-])(?:\./)?(?:[\w.-]+/)*[\w.-]+\.{_CODE_SUFFIX}(?![\w-])"
    r"(?P<node>(?:::[\w.-]+)+(?:\[[^\]\s]*\])?)?"
    r"(?P<k>\s+-k\s+(?:\"[^\"\n]{1,120}\"|'[^'\n]{1,120}'|[\w.-]+))?"
)
# A bare pytest name (``test_x``, ``TestX::test_y``), not part of a path or a longer word.
_PYTEST_NAME = re.compile(r"(?<![\w/.-])(?:Test\w+::)?test_\w+(?![\w/-])")
# A quoted span of at least three words: a JS test title when it sits next to a test word or file.
_QUOTED = re.compile(r"\"([^\"\n]{8,200})\"|“([^”\n]{8,200})”|`([^`\n]{8,200})`")
_TEST_WORD = re.compile(r"\b(?:tests?|specs?|cases?|testref)\b[\s:,(]*$", re.I)
_AFTER_FILE = re.compile(rf"^\s*(?:,\s*)?(?:\(|in\s+|from\s+|of\s+)?\s*{REF}\b", re.I)
_CHAIN = re.compile(rf"\b{REF}\s*(?:,|and|or|&)?\s*$", re.I)
_CODE_LIKE = re.compile(r"[{};=]|=>|\w\(|\bnpm\b|\bnode\b|\bpytest\b")


@dataclass(frozen=True, slots=True)
class Ref:
    start: int
    end: int
    kind: str  # path | node | name | title
    text: str


def _test_files(index: Any) -> list[str] | None:
    try:
        if index is None or not getattr(index, "is_built", False):
            return None
        return [
            p for p, rec in index.files.items() if getattr(rec, "is_test", False) or scanner.is_test_path(p)
        ]
    except Exception:  # noqa: BLE001 - an index we cannot read is no index
        return None


def _listed(path: str, tests: list[str]) -> bool:
    path = path.lstrip("./")
    return any(t == path or t.endswith("/" + path) for t in tests)


def _read(root: Any, path: str) -> str | None:
    base = os.path.realpath(str(root))
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
    return data.decode("utf-8", errors="replace")


class _Titles:
    """Test files' texts, read once and only when a quoted span needs resolving."""

    def __init__(self, index: Any, tests: list[str], named: list[str]) -> None:
        self.index, self.tests, self.named = index, tests, named
        self._texts: list[str] | None = None

    def texts(self) -> list[str]:
        if self._texts is None:
            self._texts = []
            wanted = [t for t in self.tests if any(t == n or t.endswith("/" + n) for n in self.named)]
            if not wanted:
                sizes = self.index.files
                wanted = sorted(self.tests)
                if len(wanted) > MAX_FILES or sum(sizes[p].size for p in wanted) > MAX_BYTES:
                    log.info("truthstone: test titles not resolved: test files over the cap")
                    wanted = []
            for path in wanted:
                text = _read(self.index.root, path)
                if text is not None:
                    self._texts.append(text)
        return self._texts

    def has(self, title: str) -> bool:
        return any(title in text for text in self.texts())


def refs(text: str, index: Any = None) -> list[Ref]:
    """The test references of ``text``, in order, not overlapping."""
    tests = _test_files(index)
    out: list[Ref] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    named_files: list[str] = []
    for m in _PATH.finditer(text):
        path = m.group(0).split("::", 1)[0].split()[0].lstrip("./")
        node = bool(m.group("node") or m.group("k"))
        if tests is not None:
            if not _listed(path, tests):
                continue
        elif not scanner.is_test_path(path):
            continue
        named_files.append(path)
        out.append(Ref(m.start(), m.end(), "node" if node else "path", m.group(0)))
        taken.append((m.start(), m.end()))
    if tests is None or any(scanner.is_test_path(t) and t.endswith(".py") for t in tests):
        for m in _PYTEST_NAME.finditer(text):
            if free(m.start(), m.end()):
                out.append(Ref(m.start(), m.end(), "name", m.group(0)))
                taken.append((m.start(), m.end()))
    titles = _Titles(index, tests, named_files) if tests else None
    # Quoted titles: next to a test word or a reference (before or after it), chained after another
    # title ("x" and "y"), or found verbatim in the repository's test files. Read left to right, so a
    # title after one already read can chain to it.
    out.sort(key=lambda r: r.start)
    for m in _QUOTED.finditer(text):
        title = next(g for g in m.groups() if g is not None)
        if len(title.split()) < 3 or _CODE_LIKE.search(title) or not free(m.start(), m.end()):
            continue
        before = _masked_before(text, m.start(), out)
        after = _masked_after(text, m.end(), out)
        near = bool(
            _TEST_WORD.search(before[-40:]) or _AFTER_FILE.match(after) or _CHAIN.search(before[-12:])
        )
        if not near and titles is not None and _ABOUT_A_TEST.search(_sentence_at(text, m.start(), m.end())):
            try:
                near = titles.has(title)
            except Exception:  # noqa: BLE001 - unresolved is no reference
                near = False
        if near:
            out.append(Ref(m.start(), m.end(), "title", title))
            taken.append((m.start(), m.end()))
            out.sort(key=lambda r: r.start)
    return out


# A quoted span is looked up in the test files only in a sentence that says something a test does or should
# do (fails, is red, passes, goes green, is fixed): the lookup reads files, the sentence costs nothing.
_ABOUT_A_TEST = re.compile(r"\b(?:fail\w*|red|broken|pass\w*|green|fix\w*)\b", re.I)


def _sentence_at(text: str, start: int, end: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start), text.rfind("? ", 0, start), -1) + 1
    stops = [i for i in (text.find(". ", end), text.find("\n", end), text.find("? ", end)) if i != -1]
    return text[left : min(stops) if stops else len(text)]


def _masked_before(text: str, at: int, found: list[Ref]) -> str:
    """The text before ``at`` with the references already found replaced by ``testref``."""
    pieces, last = [], 0
    for r in found:
        if r.end > at:
            break
        pieces.append(text[last : r.start])
        pieces.append(REF)
        last = r.end
    pieces.append(text[last:at])
    return "".join(pieces)


def _masked_after(text: str, at: int, found: list[Ref]) -> str:
    rest = [r for r in found if r.start >= at]
    if not rest:
        return text[at : at + 60]
    nxt = rest[0]
    return text[at : nxt.start] + REF + text[nxt.end : nxt.end + 20]


def mask(text: str, index: Any = None, kinds: frozenset[str] | None = None) -> str:
    """``text`` with each test reference (of ``kinds``, default all) replaced by ``testref``."""
    try:
        found = [r for r in refs(text, index) if kinds is None or r.kind in kinds]
    except Exception:
        log.info("truthstone: test references not read", exc_info=True)
        return text
    pieces, last = [], 0
    for r in sorted(found, key=lambda r: r.start):
        pieces.append(text[last : r.start])
        pieces.append(REF)
        last = r.end
    pieces.append(text[last:])
    return "".join(pieces)
