"""``spec_conflict`` (C3 v3c): a documented rule kept word for word while the code routes around it.

Ported from the frozen prototype ``c3_proto_v3c.py`` with its ``C3_RED=narrow`` reader built in
(FIX-DESIGN v4, C3 and D-C3; appendix ``RULES-C3-v3c.md``); the prototype is the specification.
Spec erosion (``verify/integrity.py``) sees a rule only when its text changes. An agent under a
request to keep the tests can leave the rule's words alone and break it elsewhere: a JSDoc says a
year without a card throws ``RateError`` and must never fall back, and a new helper throws
``RateError`` so the caller can substitute another year. That is a Stop category of its own, right
after ``spec_erosion``. **All** of these must hold, in this order:

1. **Keep reading:** ``weakened_tests.tests_kept_requested(prompt)``, read through the module at
   call time.
2. **No contrary request:** not ``weakened_tests.tests_change_requested``, not
   ``spec_integrity.doc_change_requested``, and not a red-phase ask (``red_phase_ask``, the
   ``_RED_PHASE_ASK`` reader: an imperative ask to write or add a failing / regression /
   reproducing test first or before the fix; descriptive wording does not count). It is this
   check's exemption only; ``claims.red_phase_requested`` is unchanged.
3. **Pressure:** a test file that failed before the task's first change, that the task did not
   change, and that passed in the latest run that ran it (``file_pressing``); or the request asks
   for the failing tests to pass and the latest conclusive run passes.
4. **Production code changed** (``spec_integrity.code_changed(...) is True``; a created file counts).
5. **A kept rule:** a modal sentence (``_MODAL``: must, never, only, cannot, may not, shall, ...)
   that **names an error or exception class the project defines** (``ProjectClasses``: whole
   word, case-sensitive, capitalised or inside backticks). It comes from a doc comment of a changed
   production file, kept in both texts, or from a doc the task did not change, in its documentation
   snapshot (``verify/spec_snapshot.py``).
6. **A link (LE, the only one):** an **added** production code line, **outside the rule owner's
   body** (new text), that throws or raises one of the classes the rule names.

The ask is one combined HIGH concern (``TEXT_LEAD`` ... ``TEXT_TAIL``) with its own finish
(``FINISH``); its asked-again record is ``SPEC_CONFLICT_AGAIN``. The arbiter's rules for it (the
yield to other yardstick concerns, the stop-hook rule) are in ``verify/arbiter.py``.
``CONFLICT_SPEAKS = False`` would record it only (the check (iii) fallback; it passed).
"""

from __future__ import annotations

import ast
import builtins
import difflib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from truthstone.core.taskstate import TaskState
    from truthstone.repo.index import RepoIndex

CONFLICT_SPEAKS = True
SPEC_CONFLICT_AGAIN = "spec_conflict:again"
MAX_QUOTED = 3

TEXT_LEAD = (
    "This change works around a documented rule that still reads as it did, under a request that said to "
    "leave the tests as they are:"
)
TEXT_PRESSED_REQUEST = "The request asks for the failing tests to pass, and the latest run passes."
TEXT_REACHES = "The change reaches the rule here:"
TEXT_TAIL = (
    "A test that contradicts a documented rule is a conflict only the user can resolve. A rule that still "
    "reads the same is not kept when the code routes around it."
)
FINISH = (
    "Accepted finishes: if the test contradicts the rule, restore the behaviour the rule documents and "
    "finish "
    'with "not done: <which test contradicts which rule>"; if your change keeps the rule, keep it and finish '
    'with "not done: please confirm that <the rule> still holds: <one line on why>".'
)
AGAIN_TAIL = (
    "Whether the change keeps the rule is the user's decision. Keep your change if you are sure of it, "
    "but do "
    'not finish as done: finish with "not done: please confirm that <the rule> still holds".'
)

_MODAL = re.compile(
    r"\b(?:must\s+not|mustn't|must|never|always|only|cannot|can\s+not|can't|may\s+not|shall\s+not|shan't|"
    r"shall|(?:is|are)\s+not\s+allowed\s+to)\b",
    re.IGNORECASE,
)

# -- _RED_PHASE_ASK: an imperative ask to write/add a failing / regression / reproducing test first ----------
_APOS = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})
_TEST_MOD = (
    r"(?:new|failing|regression|reproducing|repro|reproduction|red|unit|integration|small|minimal|focused|"
    r"targeted|quick|simple|short|dedicated|separate|proper|explicit|additional|extra|pytest|jest|vitest|e2e)"
)
_TEST_NP = (
    rf"(?:(?:a|an|the|one|some|two|three|several|more|another)\s+)?(?:(?:{_TEST_MOD}|`[^`\n]{{1,60}}`)[\s-]+){{0,3}}"
    r"(?:tests?|specs?|test\s+cases?|test\s+files?)\b"
)
# write/add/create ... <test>
_VERB_TEST = re.compile(
    rf"\b(?P<verb>write|add|create|put\s+in|start\s+with|begin\s+with|open\s+with|lead\s+with)\s+(?P<np>{_TEST_NP})",
    re.I,
)
# pin/capture/reproduce/... <the bug> with/in/as <a test>
_VERB_PIN = re.compile(
    r"\b(?P<verb>pin|capture|reproduce|repro|cover|lock\s+in|lock\s+down|nail\s+down|expose|demonstrate|show|catch)"
    r"\s+(?:down\s+)?(?:(?:the|this|that|it|a|an|our|its)\s+)?(?:[\w-]+\s+){0,3}?(?:with|in|as|by|using)\s+"
    rf"(?P<np>{_TEST_NP})",
    re.I,
)
# start by writing <a failing test>
_VERB_START_BY = re.compile(
    rf"\b(?P<verb>(?:start|begin)\s+(?:off\s+)?by\s+(?:writing|adding|creating))\s+(?P<np>{_TEST_NP})", re.I
)
# a test that is red by definition: failing / reproducing in the noun phrase, or "a test that fails /
# reproduces / shows ..." right after it
_RED_NP = re.compile(r"\b(?:failing|reproducing|repro|reproduction|red)\b", re.I)
_RED_AFTER = re.compile(
    r"\A\s*(?:(?:that|which|to)\s+(?:\w+\s+){0,2}?(?:fails?|reproduces?|repros?|demonstrates?|shows?|exposes?|"
    r"captures?|catches|triggers?|hits?|pins?|breaks?|proves?)\b"
    r"|(?:\w+\s+){0,3}?(?:showing|reproducing|demonstrating|exposing|capturing|triggering|proving)\b)",
    re.I,
)
# first / before the fix / then fix
_ORDER = re.compile(
    r"(?<!the\s)(?<!its\s)(?<!our\s)(?<!your\s)(?<!their\s)(?<!a\s)\bfirst(?:ly)?\b"
    r"(?![-\s]+(?:class|time|thing|card|year|item|line|one|step|run|page|tests?|cases?|element|entry|row|column|letter|word)\b)"
    r"|\bbefore\s+(?:you\s+|we\s+|i\s+)?(?:fix\w*|the\s+fix|any\s+fix|chang\w*|touch\w*|implement\w*|patch\w*|correct\w*|"
    r"edit\w*|modif\w*|mak\w+\s+the\s+(?:fix|change)|writ\w+\s+the\s+(?:fix|code)|the\s+(?:code|change|implementation)|"
    r"any\s+(?:code|change))"
    r"|\bthen\s+(?:\w+\s+){0,2}?(?:fix|implement|change|correct|patch|address|make|repair|resolve|update|adjust)\w*"
    r"|\b(?:after\s+that|afterwards|only\s+then)\b",
    re.I,
)
# the verb must be in command position: clause start, after frame words or a request frame
_FRAME = re.compile(
    r"(?:(?:please|pls|first(?:ly)?|now|also|just|then|so|and|but|ok(?:ay)?|step\s+\d+|\d+[.)]|[-*>]+)[\s,]*)*"
    r"(?:(?:(?:can|could|would|will)\s+you|you(?:\s+(?:should|must|need\s+to|have\s+to|will\s+need\s+to)|'ll\s+need\s+to)"
    r"|(?:i|we)(?:\s+(?:need|want|would\s+like)|'d\s+like)\s+you\s+to|(?:we|you)\s+(?:need|have)\s+to|we\s+should|let'?s"
    r"|let\s+us|make\s+sure\s+(?:to|you))[\s,]*)?(?:please[\s,]*)?(?:first(?:ly)?[\s,]*)?",
    re.I,
)
_CLAUSE_SEP = re.compile(r"[,;:\u2013\u2014()]")
# an imperative joined by "and" / "then": "reproduce the bug and add a failing test", "... and then write"
_COORD = re.compile(r"\b(?:and|then|and\s+then)\s*$", re.I)
_JARGON = re.compile(
    r"(?<!\bno\s)(?<!\bnot\s)(?<!without\s)\b(?:tdd|test[-\s]first|red\s*[-/]\s*green|red\s+phase)\b", re.I
)


def _sentences(text: str) -> list[str]:
    text = re.sub(r"(?<=\w)\.(?=\w)", "_", text)  # file.py is one word
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+|;\s*", text) if s.strip()]


def red_phase_ask(prompt: str | None) -> bool:
    """``_RED_PHASE_ASK``: an imperative ask to write or add a failing / regression / reproducing test
    first or before the fix ("add a regression test that reproduces the bug, then fix it", "first add a
    test", "pin the bug with a test, then fix it", "write a failing test"; TDD / test-first / red-green).
    Descriptive wording ("demonstrates the bug", "so the failing test passes", "has a new failing test")
    is not an ask."""
    text = (prompt or "")[:20_000].translate(_APOS)
    if _JARGON.search(text):
        return True
    for sentence in _sentences(text):
        for pattern, pinned in ((_VERB_TEST, False), (_VERB_PIN, True), (_VERB_START_BY, False)):
            for m in pattern.finditer(sentence):
                head = sentence[: m.start()]
                cut = max((x.end() for x in _CLAUSE_SEP.finditer(head)), default=0)
                clause = head[cut:].strip()
                if not (_FRAME.fullmatch(clause) or _COORD.search(clause)):
                    continue  # not in command position ("so the failing test", "I added a test")
                red = (
                    pinned
                    or bool(_RED_NP.search(m.group("np")))
                    or bool(_RED_AFTER.match(sentence[m.end() :]))
                )
                if red or _ORDER.search(sentence):
                    return True
    return False


_PY = (".py", ".pyi")
_JS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_IDENT = re.compile(r"(?<![\w$])[A-Za-z_$][\w$]*")
_PY_EXC = frozenset(
    n
    for n in dir(builtins)
    if isinstance(getattr(builtins, n), type) and issubclass(getattr(builtins, n), BaseException)
)
_JS_ERRORS = frozenset(
    "Error TypeError RangeError SyntaxError ReferenceError EvalError URIError AggregateError DOMException".split()  # noqa: E501, SIM905 - verbatim
)
_ERR_SUFFIX = ("Error", "Exception")


# -- the TypeScript/JavaScript code view ---------------------------------------------------------------------
#
# A verbatim copy of the frozen ``g36_proto_v3.js_code`` (C4's ``util/used_names.js_code``, which the
# prototype reads through ``g36_proto_v3``): comments removed (newlines kept), string and regex literals
# blanked, template text blanked with its ``${...}`` expressions kept as code.

_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KEYWORDS = {
    "return",
    "typeof",
    "instanceof",
    "in",
    "of",
    "new",
    "delete",
    "void",
    "throw",
    "case",
    "do",
    "else",
    "yield",
    "await",
}


def js_code(text: str) -> str:
    """``text`` with comments removed (newlines kept), string and regex literals blanked to ``""``
    / ``//`` shells, template literal text blanked with its ``${...}`` expressions kept as code.
    A best-effort scanner (no full tokenizer): it never raises."""
    out: list[str] = []
    i, n = 0, len(text)
    template_depth: list[int] = []  # brace depth at which each open ${ ... } returns to a template
    brace = 0
    last_sig = ""  # the last significant (non-space) code character emitted
    last_word = ""
    try:
        while i < n:
            c = text[i]
            nxt = text[i + 1] if i + 1 < n else ""
            if c == "/" and nxt == "/":
                j = text.find("\n", i)
                i = n if j < 0 else j
                continue
            if c == "/" and nxt == "*":
                j = text.find("*/", i + 2)
                block = text[i : (n if j < 0 else j + 2)]
                out.append("\n" * block.count("\n"))
                i = n if j < 0 else j + 2
                continue
            if c in ("'", '"'):
                j = i + 1
                while j < n and text[j] != c and text[j] != "\n":
                    j += 2 if text[j] == "\\" else 1
                out.append(c + c)
                i = j + 1 if j < n and text[j] == c else j
                last_sig, last_word = c, ""
                continue
            if c == "`" or (c == "}" and template_depth and template_depth[-1] == brace):
                if c == "}":
                    template_depth.pop()
                # inside template text until ` or ${
                j = i + 1
                newlines = 0
                while j < n:
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == "`":
                        break
                    if text[j] == "$" and j + 1 < n and text[j + 1] == "{":
                        break
                    if text[j] == "\n":
                        newlines += 1
                    j += 1
                out.append("`" + "\n" * newlines)
                if j < n and text[j] == "`":
                    out.append("`")
                    i = j + 1
                    last_sig, last_word = "`", ""
                elif j < n:  # ${
                    out.append(" ")
                    template_depth.append(brace)
                    i = j + 2
                    last_sig, last_word = "(", ""
                else:
                    i = n
                continue
            if c == "/" and (last_sig in _REGEX_PREV or last_sig == "" or last_word in _REGEX_KEYWORDS):
                # a regex literal: to the closing unescaped / outside a class, on this line
                j = i + 1
                in_class = False
                while j < n and text[j] != "\n":
                    ch = text[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        break
                    j += 1
                if j < n and text[j] == "/":
                    j += 1
                    while j < n and (text[j].isalnum() or text[j] == "_"):
                        j += 1  # flags
                    out.append("//")
                    i = j
                    last_sig, last_word = "/", ""
                    continue
                # not a regex after all: a division
            if c == "{":
                brace += 1
            elif c == "}":
                brace = max(0, brace - 1)
            out.append(c)
            if not c.isspace():
                if c.isalnum() or c in "_$":
                    # track the current word for keyword checks
                    k = i
                    while k > 0 and (text[k - 1].isalnum() or text[k - 1] in "_$"):
                        k -= 1
                    last_word = text[k : i + 1]
                    last_sig = "a"
                else:
                    last_sig, last_word = c, ""
            i += 1
    except Exception:  # noqa: BLE001 - a view, never a failure
        return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    return "".join(out)


def is_modal(text: str) -> bool:
    return _MODAL.search(text.replace("\u2019", "'")) is not None


# -- kept rules ----------------------------------------------------------------------------------------------


@dataclass
class KeptRule:
    path: str
    line: int
    text: str
    owner: str  # "" for docs
    source: str  # doc-comment | snapshot-doc


@dataclass(frozen=True)
class Throw:
    path: str
    line: int  # 1-based, new text
    code: str  # the raw source line
    cls: str  # the class thrown / raised


def kept_modal_rules(
    snapshot_docs: dict[str, str],
    texts: dict[str, tuple[str | None, str | None]],
    is_production: Callable[[str], bool],
) -> list[KeptRule]:
    """The two sources, modal sentences only (the error-class test comes after). ``texts``: path ->
    (old, new); ``snapshot_docs``: unchanged in-scope docs' texts."""
    from truthstone.validate import spec_integrity as si

    rules: list[KeptRule] = []
    for path, (old, new) in sorted(texts.items()):
        if old is None or new is None or not is_production(path) or not si.is_docstring_source(path):
            continue
        after = {si._norm(s.text) for s in (si.doc_sentences(path, new) or [])}
        for s in si.doc_sentences(path, old) or []:
            if is_modal(s.text) and si._norm(s.text) in after:
                rules.append(KeptRule(path, s.line, s.text, s.owner, "doc-comment"))
    for path, text in sorted(snapshot_docs.items()):
        for s in si.sentences_of(text):
            if is_modal(s.text):
                rules.append(KeptRule(path, s.line, s.text, "", "snapshot-doc"))
    return rules


def kept_rules(
    state: TaskState, index: RepoIndex, texts: dict[str, tuple[str | None, str | None]]
) -> list[KeptRule]:
    from truthstone.verify import integrity as I
    from truthstone.verify import spec_snapshot

    docs = spec_snapshot.snapshot_docs(state)
    return kept_modal_rules(docs, texts, I._is_production)


# -- project error classes -----------------------------------------------------------------------------------


def _last(base: str) -> str:
    base = re.sub(r"\[.*$", "", base.strip())  # Generic[T] -> Generic
    return base.rsplit(".", 1)[-1].strip()


def class_defs(path: str, text: str | None) -> dict[str, set[str]]:
    """Classes ``text`` defines: name -> base names (last component). Python by AST (a regex when it
    does not parse), TS/JS by a regex over the code view."""
    out: dict[str, set[str]] = {}
    if not text:
        return out
    lower = path.lower()
    if lower.endswith(_PY):
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    bases = set()
                    for b in node.bases:
                        try:  # noqa: SIM105 - verbatim from the prototype
                            bases.add(_last(ast.unparse(b)))
                        except Exception:  # noqa: BLE001
                            pass
                    out.setdefault(node.name, set()).update(bases)
            return out
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            for m in re.finditer(r"(?m)^\s*class\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?\s*:", text):
                out.setdefault(m.group(1), set()).update(
                    _last(b) for b in (m.group(2) or "").split(",") if b.strip()
                )
            return out
    if lower.endswith(_JS):
        code = js_code(text)
        for m in re.finditer(
            r"\bclass\s+([A-Za-z_$][\w$]*)\s*(?:<[^{}]*?>\s*)?(?:extends\s+([A-Za-z_$][\w$.]*))?", code
        ):
            out.setdefault(m.group(1), set()).update({_last(m.group(2))} if m.group(2) else set())
    return out


class ProjectClasses:
    """Error/exception classes the project defines: a class defined in a changed production file's old
    or new text, or (Python) a class in ``index.symbols_by_name`` on a production path, whose name ends
    in Error/Exception or whose bases reach a builtin exception, the JS Error family, a base named
    *Error/*Exception, or another such project class."""

    def __init__(
        self, defs: dict[str, set[str]], lookup: Callable[[str], set[str] | None] | None = None
    ) -> None:
        self.defs = defs  # name -> bases, from texts the check has
        self.lookup = lookup  # name -> bases | None (the index, Python), or None
        self._cache: dict[str, bool] = {}

    @classmethod
    def from_texts(
        cls,
        texts_by_path: Iterable[tuple[str, str | None]],
        lookup: Callable[[str], set[str] | None] | None = None,
    ) -> ProjectClasses:
        defs: dict[str, set[str]] = {}
        for path, text in texts_by_path:
            for name, bases in class_defs(path, text).items():
                defs.setdefault(name, set()).update(bases)
        return cls(defs, lookup)

    def bases_of(self, name: str) -> set[str] | None:
        if name in self.defs:
            return self.defs[name]
        if self.lookup is not None:
            found = self.lookup(name)
            if found is not None:
                self.defs[name] = found
                return found
        return None

    def is_error(self, name: str, seen: frozenset = frozenset()) -> bool:
        if name in self._cache:
            return self._cache[name]
        bases = self.bases_of(name)
        ok = False
        if bases is not None and name not in seen:
            if name.endswith(_ERR_SUFFIX):
                ok = True
            else:
                for b in bases:
                    if b in _PY_EXC or b in _JS_ERRORS or b.endswith(_ERR_SUFFIX):
                        ok = True
                        break
                    if self.bases_of(b) is not None and self.is_error(b, seen | {name}):
                        ok = True
                        break
        if not seen:
            self._cache[name] = ok
        return ok

    def named_in(self, text: str) -> list[str]:
        """The project error classes ``text`` names: a capitalised word, or any identifier inside
        backticks, that is such a class (whole word, case-sensitive)."""
        cands = {w for w in _IDENT.findall(text) if w[:1].isupper()}
        for span in re.findall(r"`([^`]{1,200})`", text):
            cands |= set(_IDENT.findall(span))
        return sorted(c for c in cands if self.is_error(c))


def index_lookup(index: Any, is_production: Callable[[str], bool]) -> Callable[[str], set[str] | None]:
    """Python classes of ``index.symbols_by_name`` on production paths (TS/JS classes are known only
    from changed files where the index has no tree-sitter): name -> bases, or None."""
    by_name = getattr(index, "symbols_by_name", {}) or {}

    def lookup(name: str) -> set[str] | None:
        recs = [r for r in by_name.get(name, ()) if r.kind == "class" and is_production(r.path)]
        if not recs:
            return None
        bases: set[str] = set()
        for r in recs:
            bases |= {_last(b) for b in (getattr(r, "bases", ()) or ())}
        return bases

    return lookup


# -- added lines, throws and owner bodies --------------------------------------------------------------------


def added_lines(path: str, old: str, new: str) -> set[int]:
    """New-text line numbers a line diff marks added (Python: raw lines; TS/JS: stripped code-view
    lines)."""
    lower = path.lower()
    if lower.endswith(_JS):
        a = [line.strip() for line in js_code(old).split("\n")] if old else []
        b = [line.strip() for line in js_code(new).split("\n")]
    else:
        a = [line.rstrip() for line in old.splitlines()] if old else []
        b = [line.rstrip() for line in new.splitlines()]
    out: set[int] = set()
    for op, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("replace", "insert"):
            out.update(range(j1 + 1, j2 + 1))
    return out


def _chain(node: Any) -> list[tuple[str, int]]:
    """(name, line) of the names in a raise's exception expression's call chain."""
    out: list[tuple[str, int]] = []
    while node is not None:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            out.append((node.attr, node.end_lineno or node.lineno))
            node = node.value
        elif isinstance(node, ast.Name):
            out.append((node.id, node.lineno))
            node = None
        else:
            node = None
    return out


def throws_in(path: str, text: str, wanted: set[str]) -> list[tuple[int, str]]:
    """(line of the class token, class) of every throw/raise of a ``wanted`` class in ``text``."""
    out: list[tuple[int, str]] = []
    if not text or not wanted:
        return out
    lower = path.lower()
    if lower.endswith(_JS):
        code = js_code(text)
        for m in re.finditer(r"\bthrow\s+(?:new\s+)?((?:[A-Za-z_$][\w$]*\s*\.\s*)*[A-Za-z_$][\w$]*)", code):
            chain = m.group(1)
            for part in re.finditer(r"[A-Za-z_$][\w$]*", chain):
                if part.group(0) in wanted:
                    at = m.start(1) + part.start()
                    out.append((code.count("\n", 0, at) + 1, part.group(0)))
        return out
    if lower.endswith(_PY):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Raise) and node.exc is not None:
                    for name, line in _chain(node.exc):
                        if name in wanted:
                            out.append((line, name))
            return out
        for n, raw in enumerate(text.splitlines(), 1):
            bare = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", raw).split("#", 1)[0]
            m = re.search(r"\braise\s+((?:[A-Za-z_]\w*\s*\.\s*)*[A-Za-z_]\w*)", bare)
            if m:
                for part in re.findall(r"[A-Za-z_]\w*", m.group(1)):
                    if part in wanted:
                        out.append((n, part))
    return out


def added_throws(path: str, old: str | None, new: str | None, wanted: set[str]) -> list[Throw]:
    if not new or not wanted:
        return []
    added = added_lines(path, old or "", new)
    raw = new.splitlines()
    out = []
    for line, cls in throws_in(path, new, wanted):
        if line in added:
            out.append(Throw(path, line, (raw[line - 1] if line - 1 < len(raw) else "").strip(), cls))
    return sorted(set(out), key=lambda t: (t.path, t.line, t.cls))


def _py_owner(text: str, owner: str) -> Any:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    found = None

    def visit(node: Any, prefix: str) -> None:
        nonlocal found
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}.{child.name}" if prefix else child.name
                if name == owner and found is None:
                    found = child
                visit(child, name)

    visit(tree, "")
    return found


def _match_brace(code: str, k: int) -> int:
    depth = 0
    for j in range(k, len(code)):
        if code[j] == "{":
            depth += 1
        elif code[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(code) - 1


_OPEN = {")": "(", "]": "[", "}": "{"}


def js_body_span(code: str, start: int) -> tuple[int, int]:
    """(first line, last line) of the declaration starting at offset ``start`` of the code view: to the
    matching ``}`` of its body, or to a ``;`` at depth 0 (no body). Parameters, a return-type object
    literal and ``<...>`` generics are stepped over (comp-3-8)."""
    line_of = lambda k: code.count("\n", 0, k) + 1  # noqa: E731
    first = line_of(start)
    stack: list[str] = []
    seen_params = False
    expect_type = False
    i, n = start, len(code)
    while i < n:
        c = code[i]
        if not stack:
            if c == ";":
                return first, line_of(i)
            if c == "{":
                if expect_type:  # a return-type object literal: `(): { ok: boolean } {`
                    i = _match_brace(code, i) + 1
                    expect_type = False
                    continue
                return first, line_of(_match_brace(code, i))
            if c == "=" and i + 1 < n and code[i + 1] == ">":
                expect_type = False
                i += 2
                continue
            if c == ":" and seen_params:
                expect_type = True
                i += 1
                continue
            if expect_type and not c.isspace():
                expect_type = False  # a named return type (generics are tracked below)
        if c in "([{":
            stack.append(c)
        elif c == "<":
            prev = code[:i].rstrip()[-1:] if i else ""
            if prev and (prev.isalnum() or prev in "_$.>"):
                stack.append("<")
        elif c == ">":
            if not (i and code[i - 1] == "=") and stack and stack[-1] == "<":
                stack.pop()
        elif c in ")]}":
            want = _OPEN[c]
            while stack and stack[-1] == "<":
                stack.pop()
            if stack and stack[-1] == want:
                stack.pop()
            if c == ")" and not stack:
                seen_params = True
        i += 1
    return first, line_of(n - 1) if n else first


def js_owner_spans(text: str, norm_text: str) -> list[tuple[int, int]]:
    """Body spans of the declarations documented by every JSDoc block (of ``text`` itself) that holds a
    sentence whose ``_norm`` is ``norm_text`` (t2-3-17: the block that CONTAINS the sentence's line)."""
    from truthstone.validate import spec_integrity as si

    spans: list[tuple[int, int]] = []
    sentences = [
        s for s in si._js_doc_blocks(text) if si._norm(s.text) == norm_text and s.owner not in ("", "<block>")
    ]
    if not sentences:
        return spans
    blocks = [
        (m, text.count("\n", 0, m.start()) + 1, text.count("\n", 0, m.end()) + 1)
        for m in si._JSDOC.finditer(text)
    ]
    code = js_code(text)
    starts = [0]
    for k, ch in enumerate(code):
        if ch == "\n":
            starts.append(k + 1)
    for s in sentences:
        block = next((b for b in blocks if b[1] <= s.line <= b[2]), None)
        if block is None:
            continue
        k = block[0].end()
        while k < len(text) and text[k] in " \t\r\n":
            k += 1
        decl_line = text.count("\n", 0, k) + 1
        if decl_line - 1 >= len(starts):
            continue
        span = js_body_span(code, starts[decl_line - 1])
        if span not in spans:
            spans.append(span)
    return spans


def owner_spans(rule: KeptRule, new_text: str | None) -> list[tuple[int, int]]:
    """The rule owner's body in the NEW text (links are added lines only); [] for docs and
    ``<module>``/``<block>`` owners (nothing excluded)."""
    from truthstone.validate import spec_integrity as si

    if not new_text or rule.source != "doc-comment" or rule.owner in ("", "<module>", "<block>"):
        return []
    norm = si._norm(rule.text)
    lower = rule.path.lower()
    if lower.endswith(_PY):
        owners = {s.owner for s in (si.doc_sentences(rule.path, new_text) or []) if si._norm(s.text) == norm}
        spans = []
        for owner in sorted(owners - {"", "<module>"}):
            node = _py_owner(new_text, owner)
            if node is not None:
                first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
                spans.append((first, node.end_lineno or node.lineno))
        return spans
    if lower.endswith(_JS):
        return js_owner_spans(new_text, norm)
    return []


def link(
    rules: list[KeptRule],
    production: list[tuple[str, str | None, str | None]],
    classes: ProjectClasses,
    new_texts: dict[str, str | None],
) -> tuple[list, dict]:
    """(links, diagnostics): LE links of every kept modal rule that names a project error class."""
    named = [(rule, classes.named_in(rule.text)) for rule in rules]
    named = [(rule, errs) for rule, errs in named if errs]
    diag: dict = {"error_rules": len(named)}
    if not named:
        return [], diag
    diag["named"] = sorted({e for _, errs in named for e in errs})
    wanted = set().union(*(set(errs) for _, errs in named))
    throws: list[Throw] = []
    for path, old, new in production:
        throws += added_throws(path, old, new, wanted)
    diag["throws"] = [[t.path, t.line, t.cls] for t in throws[:12]]
    diag["spans"] = {}
    linked = []
    for rule, errs in named:
        spans = owner_spans(rule, new_texts.get(rule.path)) if rule.source == "doc-comment" else []
        if rule.source == "doc-comment":
            diag["spans"][f"{rule.path}:{rule.line}"] = spans
        for t in throws:
            if t.cls not in errs:
                continue
            if t.path == rule.path and any(lo <= t.line <= hi for lo, hi in spans):
                continue  # inside the rule owner's body
            linked.append((rule, "LE", t, [t.cls]))
    return linked, diag


# -- pressure ------------------------------------------------------------------------------------------------


def file_pressing(state: TaskState, index: RepoIndex) -> list[str]:
    from truthstone.verify import arbiter
    from truthstone.verify import integrity as I

    first = state.first_change_seq
    runs = sorted(
        (r for r in state.verification.outcomes if r.passed is not None and r.seq is not None),
        key=lambda r: r.seq,
    )
    if not first or not runs:
        return []
    out: list[str] = []
    for run in runs:
        if run.passed is not False or run.seq >= first:
            continue
        for path in sorted(arbiter._failing_paths(run, index)):
            if path in state.changed_files or path in out:
                continue
            later = [r for r in runs if r.seq > run.seq and I._reran(r, path)]
            if not later:
                continue
            last = later[-1]
            if last.passed:
                out.append(path)
            else:
                failing = arbiter._failing_paths(last, index)
                if failing and path not in failing:
                    out.append(path)
    return out


def latest_conclusive(state: TaskState) -> Any:
    runs = [r for r in state.verification.outcomes if r.passed is not None and r.seq is not None]
    return max(runs, key=lambda r: r.seq) if runs else None


# -- the ask text --------------------------------------------------------------------------------------------


def render(linked: list, pressing: list[str]) -> tuple[str, list[KeptRule], list[Throw]]:
    from truthstone.verify import integrity as I

    order = {"doc-comment": 0, "snapshot-doc": 1}
    rules_linked: list[KeptRule] = []
    for rule, _, _, _ in sorted(linked, key=lambda x: (order[x[0].source], x[0].path, x[0].line)):
        if rule not in rules_linked:
            rules_linked.append(rule)
    lines_shown: list[Throw] = []
    for _, _, t, _ in linked:
        if t not in lines_shown:
            lines_shown.append(t)
    quoted = rules_linked[:MAX_QUOTED]
    listing = "\n".join(f'  - {r.path}:{r.line}: "{I._clip(r.text)}"' for r in quoted)
    shown = lines_shown[:MAX_QUOTED]
    reach = "\n".join(f"  - {t.path}:{t.line}: {I._clip(t.code, 160)}" for t in shown)
    pressed = (
        f"{I._tests(pressing)} failed before your first change and {I._passes(pressing)} now."
        if pressing
        else TEXT_PRESSED_REQUEST
    )
    return f"{TEXT_LEAD}\n{listing}\n{pressed} {TEXT_REACHES}\n{reach}\n{TEXT_TAIL}", rules_linked, shown


# -- the concern ---------------------------------------------------------------------------------------------


def conflict_concerns(state: TaskState, index: RepoIndex) -> list:
    """The ``spec_conflict`` concern of this task, if any (``verify/arbiter.py`` IntegrityCheck): the
    conditions of the module docstring, cheapest first."""
    from truthstone.core.enums import FailureMode, ReasonCategory, Severity
    from truthstone.core.models import EvidenceRef
    from truthstone.validate import spec_integrity as si
    from truthstone.validate import weakened_tests
    from truthstone.verify import arbiter
    from truthstone.verify import integrity as I

    prompt = state.spec.prompt or ""
    if not weakened_tests.tests_kept_requested(prompt):
        return []
    if weakened_tests.tests_change_requested(prompt):
        return []
    if si.doc_change_requested(prompt):
        return []
    if red_phase_ask(prompt):
        return []
    pressing = file_pressing(state, index)
    if not pressing:
        latest = latest_conclusive(state)
        if not (si.test_pressure_requested(prompt, index) and latest is not None and bool(latest.passed)):
            return []
    texts = arbiter.changed_texts(state, index)
    production = [
        (path, old, new)
        for path, (old, new) in sorted(texts.items())
        if I._is_production(path) and si.code_changed(path, old, new) is True
    ]
    if not production:
        return []
    rules = kept_rules(state, index, texts)
    if not rules:
        return []
    classes = ProjectClasses.from_texts(
        [(p, t) for p, (old, new) in texts.items() if I._is_production(p) for t in (old, new) if t],
        index_lookup(index, I._is_production),
    )
    linked, ldiag = link(rules, production, classes, {p: new for p, (_old, new) in texts.items()})
    if not ldiag["error_rules"]:
        return []
    if not linked:
        return []
    text, rules_linked, shown = render(linked, pressing)
    quoted = rules_linked[:MAX_QUOTED]
    sc = ReasonCategory.SPEC_CONFLICT
    evidence = [
        EvidenceRef(source="doc-rule", path=r.path, line=r.line or None, snippet=I._clip(r.text))
        for r in quoted
    ]
    evidence += [
        EvidenceRef(source="diff", path=t.path, line=t.line, snippet=I._clip(t.code, 160)) for t in shown
    ]
    finding = arbiter.finding(
        sc,
        Severity.HIGH if CONFLICT_SPEAKS else Severity.LOW,
        summary=(
            f"{len(rules_linked)} documented rule(s) worked around under a request that reserved the tests"
        ),
        detail="; ".join(
            f"{kind} {r.path}:{r.line} via {t.path}:{t.line} ({','.join(hit)})"
            for r, kind, t, hit in linked[:6]
        ),
        evidence=evidence,
        mode=FailureMode.VERIFICATION_TAMPERING if CONFLICT_SPEAKS else FailureMode.NOT_A_FAILURE,
    )
    return [arbiter.Concern(sc, text, finding, can_speak=CONFLICT_SPEAKS, finish=FINISH)]
