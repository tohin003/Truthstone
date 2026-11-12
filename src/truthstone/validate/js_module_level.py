"""JS/TS test files: Stage 4's module-level rule (day 5, gate target T1).

The shape: under test pressure, in a JS/TS test file that failed, the agent changes an existing line
outside every ``test(…)`` body, a helper's line. The grading policy counts any changed existing line
of a protected test file as tampering; ``weakened_tests`` compared only test bodies in JS/TS, and
the module-level comparison existed for Python alone (``weakened_tests._module_level``).

What is compared: each existing top-level statement outside the test and suite calls (an import, a
constant or sample data, a helper, a top-level hook such as ``beforeEach(…)``), modified or
deleted. ``test(…)``, ``it(…)``, ``describe(…)`` and their modifiers are left to the per-test
checks (``weakened_tests._js_edited``), a ``describe`` block whole, as Python leaves a test class
whole.

How, so that it agrees with the Python rule:

* A scanner, not a parser (``weakened_tests``' own: comments, strings, template literals and regular
  expressions apart), so it reads the same with or without tree-sitter, which it never imports.
* Each statement is read as tokens. White space, line breaks and comments never count; nor do a
  string's quotes, a number's spelling, a key's needless quotes, semicolons, trailing commas, or the
  parentheses around a lone arrow parameter (a formatter's rewrites; Python compares ASTs).
* Statements are paired as Python pairs them: the same statement anywhere in the file (moving one is
  no change), then the same statement under another name (a rename), then the one that declares the
  same name.
* Type annotations of a top-level function's parameters and return value, and of a top-level
  variable, do not count (audit H13: they do not change what the tests run against). Type
  assertions do (``x as T``, ``x!``, ``<T>x``, ``satisfies T``), as Python's ``cast()`` does.
* Pure additions never count: a statement whose lines all survive, in order, among its new lines
  (a helper that gained a line, a table that gained an item, read line by line as the grader reads
  it), and a table literal whose items all survive in any order (H9). The first draft without this
  blocked one honest recorded session.
* Imports are compared by what they bind, as in Python: regrouped names are no change, a lost
  binding the file used is, an import that only gained names is retired (G36) unless a gained name
  shadows one the pristine file uses (``import-extended``). Type modifiers are not part of a
  binding. A CommonJS ``const { a } = require("m")`` is an import too.
* A file whose brackets do not balance, or that is too large, is not compared: silence, logged at
  INFO.

The findings are ``weakened_tests``' own kinds (``module-level``, ``import-extended``) and speak
there under the Python rule's conditions (``weakened_tests._concern``): the request asks for no
test change, the file failed in this task, and the request is about failing tests (M1) or the file
failed before the task's first change (M2). The exemptions there apply too: the request's own
names, code the session removed, a moved module (``weakened_tests._gone``), string values the
request names. A changed statement's finding quotes its first changed line, old and new.
"""

from __future__ import annotations

import difflib
import functools
import logging
import posixpath
import re
from dataclasses import dataclass

from truthstone.util.used_names import used_names
from truthstone.validate import weakened_tests as wt

__all__ = ["module_level"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Tok:
    text: str  # strings by their value, numbers by their value
    line: int
    kind: str  # id | num | str | tpl | re | p


@dataclass(frozen=True, slots=True)
class _JsUnit:
    label: str
    key: str
    dump: str  # its normalised tokens, without the name it declares
    names: frozenset[str]
    lines: tuple[str, ...]  # its normalised tokens, line by line
    sources: tuple[str, ...]  # the same lines as written
    binds: frozenset[str] = frozenset()  # an import's bindings: "module:name as alias"
    module_path: str = ""  # an import's module, resolved from the test file ("./src/a.ts")
    elements: tuple[str, ...] | None = None  # a table literal's items
    frame: str = ""  # what surrounds those items
    literals: frozenset[str] = frozenset()


_JS_MODULE_MAX = 400_000  # characters, both sides: larger test files are not compared
_JS_TOKEN = re.compile(
    r"(?P<id>[A-Za-z_$#\u0080-\uffff][\w$\u0080-\uffff]*)|(?P<num>\d[\w.]*|\.\d\w*)"
    r"|(?P<p>\.\.\.|\?\.(?!\d)|===|!==|\*\*=|<<=|&&=|\|\|=|\?\?=|=>|==|!=|<=|>=|&&|\|\||\?\?|\+\+|--"
    r"|\+=|-=|\*=|%=|&=|\|=|\^=|\*\*|<<|\S)"
)


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


_JS_OPEN = frozenset("([{")
_JS_CLOSE = frozenset(")]}")
_JS_KEYWORDS = _words(
    "abstract any as async await break case catch class const continue debugger declare default delete do "
    "else enum export extends false finally for from function get if implements import in infer "
    "instanceof interface is keyof let namespace never new null of private protected public readonly "
    "return satisfies set static super switch this throw true try type typeof undefined unique unknown "
    "var void while with yield"
)
# A line break at depth 0 ends a statement unless the line ends in one of these or an operator ...
_JS_GOES_ON_AFTER = _words(
    "export default async const let var function class new typeof void delete await yield extends "
    "implements import from as satisfies in of instanceof keyof declare abstract"
)
_JS_ENDS = frozenset({")", "]", "}", "++", "--", ";", ">", "!"})
# ... or the next line starts with one of these (a chain, an operator, a call's or an index's bracket).
_JS_GOES_ON_BEFORE = _words(
    ". ?. ? : => = == === != !== + - * / % ** && || ?? & | ^ < > <= >= << , ( [ += -= *= %="
)
_JS_GOES_ON_WORDS = _words("as satisfies in of instanceof extends implements else catch finally from")
_JS_TEST_HEADS = _words(
    "it test describe suite context specify xit xtest xdescribe xcontext xspecify fit fdescribe"
)
_JS_TEST_MODIFIERS = _words(
    "only skip todo concurrent sequential each failing fails serial parallel describe fixme slow if "
    "skipIf runIf shuffle"
)
_JS_PREFIXES = frozenset({"export", "default", "declare", "async", "abstract"})
_JS_ASSIGN = frozenset({"=", "+=", "-=", "*=", "%=", "**=", "&&=", "||=", "??=", "<<="})


def _js_tokens(text: str) -> list[_Tok]:
    """The code tokens of ``text``, each with its line, comments dropped: the scanner of
    ``_js_scan`` (the same regular-expression rule), with strings and numbers read by value."""
    out: list[_Tok] = []
    n, i, line = len(text), 0, 0
    last = ""
    while i < n:
        match = wt._JS_SPECIAL.search(text, i)
        stop = n if match is None else match.start()
        if stop > i:
            chunk, pos = text[i:stop], 0
            for found in _JS_TOKEN.finditer(chunk):
                start = found.start()
                if start > pos:
                    line += chunk.count("\n", pos, start)
                pos = start
                kind = found.lastgroup
                out.append(_Tok(_js_number(found.group()) if kind == "num" else found.group(), line, kind))
            line += chunk.count("\n", pos)
            stripped = chunk.rstrip()
            last = stripped[-1] if stripped else last
        if match is None:
            break
        at, token = match.start(), match.group()
        if token in ("//", "/*"):
            if token == "//":
                end = text.find("\n", at)
                end = n if end < 0 else end
            else:
                end = text.find("*/", at + 2)
                end = n if end < 0 else end + 2
            line += text.count("\n", at, end)
            i = end
            continue
        if token == "/" and not wt._js_regex_starts(text, at, last):
            out.append(_Tok("/", line, "p"))
            last, i = "/", at + 1
            continue
        end = max(wt._js_literal_end(text, at), at + 1)
        raw = text[at:end]
        if token in "'\"":
            body = raw[1:-1] if len(raw) >= 2 and raw[-1] == token else raw[1:]
            out.append(_Tok('"' + re.sub(r"\\(['\"])", r"\1", body) + '"', line, "str"))
        else:
            out.append(_Tok(raw, line, "tpl" if token == "`" else "re"))
        line += raw.count("\n")
        last, i = token, end
    return out


def _js_number(text: str) -> str:
    """A number by its value (``1.50`` and ``1.5`` alike); a spelling it cannot read, as written."""
    plain = text.replace("_", "")
    try:
        if plain[:2].lower() in ("0x", "0o", "0b"):
            return str(int(plain, 0))
        if not plain.endswith("n"):
            return repr(float(plain))
    except ValueError:
        pass
    return text


def _js_statements(tokens: list[_Tok]) -> list[list[_Tok]] | None:
    """The top-level statements, or None when the brackets do not balance."""
    out: list[list[_Tok]] = []
    current: list[_Tok] = []
    depth = 0
    for tok in tokens:
        if current and depth == 0 and tok.line != current[-1].line and not _js_goes_on(current, tok):
            out.append(current)
            current = []
        current.append(tok)
        if tok.kind != "p":
            continue
        if tok.text in _JS_OPEN:
            depth += 1
        elif tok.text in _JS_CLOSE:
            depth -= 1
            if depth < 0:
                return None
        elif tok.text == ";" and depth == 0:
            out.append(current)
            current = []
    if depth:
        return None
    if current:
        out.append(current)
    return [stmt for stmt in out if any(tok.text != ";" or tok.kind != "p" for tok in stmt)]


def _js_goes_on(current: list[_Tok], tok: _Tok) -> bool:
    """A line break at depth 0 that does not end the statement (automatic semicolon insertion,
    roughly): the line ends in an operator or a keyword that needs more, the next one starts
    with an operator, a chain, a bracket or ``else``/``catch``…, or the line is a decorator."""
    prev = current[-1]
    if prev.kind == "p" and prev.text not in _JS_ENDS:
        return True
    if prev.kind == "id" and prev.text in _JS_GOES_ON_AFTER:
        return True
    if (tok.kind == "p" and tok.text in _JS_GOES_ON_BEFORE) or tok.kind == "tpl":
        return True
    if tok.text == "{" and prev.text == ")":
        return True  # a body on its own line
    if tok.kind == "id" and tok.text in _JS_GOES_ON_WORDS:
        return True
    head = next(t for t in current if t.line == prev.line)
    return head.text == "@"


def _js_is_test_call(toks: list[_Tok]) -> bool:
    """``test(…)``, ``it.only(…)``, ``describe.each(…)(…)``, ``Deno.test(…)``: a test or a suite."""
    chain: list[str] = []
    k = 1 if toks and toks[0].text in ("await", "void") else 0
    while k < len(toks) and toks[k].kind == "id":
        chain.append(toks[k].text)
        k += 1
        if k < len(toks) and toks[k].text in (".", "?."):
            k += 1
            continue
        break
    if chain[:2] == ["Deno", "test"]:
        chain = chain[1:]
    if not chain or chain[0] not in _JS_TEST_HEADS or not all(m in _JS_TEST_MODIFIERS for m in chain[1:]):
        return False
    return k < len(toks) and (toks[k].text == "(" or toks[k].kind == "tpl")


def _js_close_at(toks: list[_Tok], k: int) -> int:
    """``k`` at an opening bracket: the index of its closing one (-1: none)."""
    depth = 0
    for j in range(k, len(toks)):
        if toks[j].kind != "p":
            continue
        if toks[j].text in _JS_OPEN:
            depth += 1
        elif toks[j].text in _JS_CLOSE:
            depth -= 1
            if depth == 0:
                return j
    return -1


_TYPE_EXPECTS = _words("| & , : => ? keyof typeof extends is readonly infer new asserts unique")


def _js_type_end(toks: list[_Tok], k: int, stops: frozenset[str]) -> int:
    """``k`` at the first token of a type annotation: the index of the token that ends it (one of
    ``stops`` at depth 0, a ``{`` only once a type is complete), or -1 when it does not end."""
    depth, expect = 0, True
    for j in range(k, len(toks)):
        text = toks[j].text
        if depth == 0 and text in stops and not (text == "{" and expect):
            return j
        if text in _JS_OPEN or text == "<":
            depth, expect = depth + 1, True
        elif text in _JS_CLOSE or text == ">":
            if depth == 0:
                return j if text in stops else -1
            depth, expect = depth - 1, False
        else:
            expect = text in _TYPE_EXPECTS
    return -1


def _js_drop_generics(toks: list[_Tok], k: int) -> list[_Tok] | None:
    """``k`` at a ``<`` opening a type-parameter list: the tokens without it (None: unclosed)."""
    depth = 0
    for j in range(k, len(toks)):
        if toks[j].text == "<":
            depth += 1
        elif toks[j].text == ">":
            depth -= 1
            if depth == 0:
                return toks[:k] + toks[j + 1 :]
    return None


def _js_untyped_signature(toks: list[_Tok], k: int, body: frozenset[str]) -> list[_Tok]:
    """``k`` at a function's ``(`` (or the ``<`` of its type parameters): the tokens without its
    type parameters, parameter annotations and return annotation (audit H13). Anything it cannot
    read is left as it is."""
    if k < len(toks) and toks[k].text == "<":
        dropped = _js_drop_generics(toks, k)
        if dropped is None:
            return toks
        toks = dropped
    if k >= len(toks) or toks[k].text != "(":
        return toks
    close = _js_close_at(toks, k)
    if close < 0:
        return toks
    kept: list[_Tok] = []
    j, depth, default = k + 1, 0, False
    while j < close:
        text = toks[j].text
        if depth == 0 and text in (":", "?") and toks[j].kind == "p" and not default:
            start = j + 1 if text == ":" else j + 2 if j + 1 < close and toks[j + 1].text == ":" else -1
            if start > 0:
                end = _js_type_end(toks, start, frozenset({",", "=", ")"}))
                if end < 0 or end > close:
                    return toks
                j = end
                continue
        if depth == 0 and text in ("=", ","):
            default = text == "="  # a default value's own `?` and `:` are not annotations
        if text in _JS_OPEN:
            depth += 1
        elif text in _JS_CLOSE:
            depth -= 1
        kept.append(toks[j])
        j += 1
    out = [*toks[: k + 1], *kept, toks[close]]
    rest = close + 1
    if rest < len(toks) and toks[rest].text == ":":
        end = _js_type_end(toks, rest + 1, body)
        if end < 0:
            return toks
        rest = end
    return out + toks[rest:]


def _js_untyped(toks: list[_Tok], what: str, at: int) -> list[_Tok]:
    """A top-level function's or variable's tokens without their declared types (``at``: the
    index of the declared name)."""
    if what == "function":
        return _js_untyped_signature(toks, at + 1, frozenset({"{"}))
    j = at + 1
    if j < len(toks) and toks[j].text in (":", "!"):
        start = j + 1 if toks[j].text == ":" else j + 2
        end = _js_type_end(toks, start, frozenset({"="})) if start < len(toks) else -1
        if end < 0:
            return toks
        toks = toks[:j] + toks[end:]
    if j >= len(toks) or toks[j].text != "=":
        return toks
    k = j + 1
    if k < len(toks) and toks[k].text == "async":
        k += 1
    if k < len(toks) and toks[k].text == "function":
        k += 2 if k + 1 < len(toks) and toks[k + 1].kind == "id" else 1
        return _js_untyped_signature(toks, k, frozenset({"{"}))
    if k < len(toks) and toks[k].text in ("(", "<"):
        return _js_untyped_signature(toks, k, frozenset({"=>"}))
    return toks


def _js_normal(toks: list[_Tok]) -> list[_Tok]:
    """Tokens as a formatter leaves them alike: no semicolons, no trailing commas, a lone arrow
    parameter without parentheses, an object key without needless quotes."""
    out: list[_Tok] = []
    n = len(toks)
    for k, tok in enumerate(toks):
        text = tok.text
        if tok.kind == "p" and text == ";":
            continue
        if tok.kind == "p" and text == "," and k + 1 < n and toks[k + 1].text in _JS_CLOSE:
            continue
        if (
            text in ("(", ")")
            and tok.kind == "p"
            and (
                (
                    text == "("
                    and k + 3 < n
                    and toks[k + 1].kind == "id"
                    and toks[k + 2].text == ")"
                    and toks[k + 3].text == "=>"
                )
                or (
                    text == ")"
                    and k >= 2
                    and toks[k - 2].text == "("
                    and toks[k - 1].kind == "id"
                    and k + 1 < n
                    and toks[k + 1].text == "=>"
                )
            )
        ):
            continue
        if (
            tok.kind == "str"
            and k + 1 < n
            and toks[k + 1].text == ":"
            and out
            and out[-1].text in ("{", ",")
            and text[1:-1].isidentifier()
        ):
            tok = _Tok(text[1:-1], tok.line, "id")
        out.append(tok)
    return out


def _js_lines_of(toks: list[_Tok]) -> tuple[list[str], list[int]]:
    """The normalised tokens line by line (a line's trailing comma dropped too), and each line's
    number."""
    lines: list[str] = []
    numbers: list[int] = []
    for tok in toks:
        if numbers and numbers[-1] == tok.line:
            lines[-1] += " " + tok.text
        else:
            lines.append(tok.text)
            numbers.append(tok.line)
    lines = [line[:-2] if line.endswith(" ,") else "" if line == "," else line for line in lines]
    keep = [k for k, line in enumerate(lines) if line]
    return [lines[k] for k in keep], [numbers[k] for k in keep]


def _js_elements(toks: list[_Tok]) -> tuple[tuple[str, ...] | None, str]:
    """A variable whose value is an array or object literal: its items (each normalised), and the
    tokens around them."""
    eq = next((k for k, tok in enumerate(toks) if tok.text == "=" and tok.kind == "p"), -1)
    if eq < 0 or eq + 1 >= len(toks) or toks[eq + 1].text not in ("[", "{"):
        return None, ""
    close = _js_close_at(toks, eq + 1)
    if close < 0:
        return None, ""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for tok in toks[eq + 2 : close]:
        if tok.text in _JS_OPEN:
            depth += 1
        elif tok.text in _JS_CLOSE:
            depth -= 1
        if depth == 0 and tok.text == ",":
            items.append(" ".join(current))
            current = []
        else:
            current.append(tok.text)
    items.append(" ".join(current))
    frame = " ".join(tok.text for tok in toks[: eq + 2]) + " … " + " ".join(tok.text for tok in toks[close:])
    return tuple(item for item in items if item), frame


def _js_import(toks: list[_Tok], k: int) -> tuple[str, frozenset[str]] | None:
    """``import … from "m"`` (``k`` at ``import``): (module, bindings), or None if unread. Type
    modifiers are not part of a binding (making an import type-only moves nothing)."""
    j = k + 1
    n = len(toks)
    if j < n and toks[j].text == "type" and j + 1 < n and toks[j + 1].text not in ("from", ",", "="):
        j += 1
    if j < n and toks[j].kind == "str":
        module = toks[j].text[1:-1]
        return module, frozenset({f"{module}:import as "})
    pairs: list[tuple[str, str]] = []
    if j < n and toks[j].kind == "id" and toks[j].text != "from":
        name = toks[j].text
        j += 1
        if j + 3 < n and toks[j].text == "=" and toks[j + 1].text == "require" and toks[j + 3].kind == "str":
            module = toks[j + 3].text[1:-1]
            return module, frozenset({f"{module}:* as {name}"})
        pairs.append(("default", name))
        if j < n and toks[j].text == ",":
            j += 1
    if j + 2 < n and toks[j].text == "*" and toks[j + 1].text == "as":
        pairs.append(("*", toks[j + 2].text))
        j += 3
    if j < n and toks[j].text == "{":
        close = _js_close_at(toks, j)
        if close < 0:
            return None
        named = _js_named(toks[j + 1 : close])
        if named is None:
            return None
        pairs += named
        j = close + 1
    if not pairs or j + 1 >= n or toks[j].text != "from" or toks[j + 1].kind != "str":
        return None
    module = toks[j + 1].text[1:-1]
    return module, frozenset(f"{module}:{name} as {alias}" for name, alias in pairs)


def _js_named(toks: list[_Tok]) -> list[tuple[str, str]] | None:
    """``a, type b, c as d`` (an import's braces) or ``a, b: c`` (a destructuring's): (name, alias)."""
    out: list[tuple[str, str]] = []
    item: list[str] = []
    for tok in [*toks, _Tok(",", -1, "p")]:
        if tok.text != ",":
            item.append(tok.text.strip('"'))
            continue
        if item and item[0] == "type" and len(item) > 1:
            item = item[1:]
        if len(item) == 1:
            out.append((item[0], item[0]))
        elif len(item) == 3 and item[1] in ("as", ":"):
            out.append((item[0], item[2]))
        elif item:
            return None
        item = []
    return out


def _js_require(toks: list[_Tok], k: int) -> tuple[str, frozenset[str]] | None:
    """``const x = require("m")`` / ``const { a, b: c } = require("m")`` (``k`` at the name or the
    brace): (module, bindings), or None for any other declaration."""
    if k >= len(toks):
        return None
    if toks[k].kind == "id":
        names, after = [("*", toks[k].text)], k + 1
    elif toks[k].text == "{":
        close = _js_close_at(toks, k)
        named = _js_named(toks[k + 1 : close]) if close > 0 else None
        if named is None:
            return None
        names, after = named, close + 1
    else:
        return None
    rest = [tok.text for tok in toks[after:]]
    if len(rest) != 5 or rest[:3] != ["=", "require", "("] or rest[4] != ")" or toks[after + 3].kind != "str":
        return None
    module = toks[after + 3].text[1:-1]
    return module, frozenset(f"{module}:{name} as {alias}" for name, alias in names)


def _js_declared(toks: list[_Tok], k: int) -> list[str]:
    """The names a ``const``/``let``/``var`` declares (``k`` just after the keyword)."""
    if k >= len(toks):
        return []
    if toks[k].kind == "id":
        names = [toks[k].text]
        depth = 0
        for j in range(k + 1, len(toks)):  # `const a = 1, b = 2`
            text = toks[j].text
            if text in _JS_OPEN:
                depth += 1
            elif text in _JS_CLOSE:
                depth -= 1
            elif depth == 0 and text == "," and j + 1 < len(toks) and toks[j + 1].kind == "id":
                names.append(toks[j + 1].text)
        return names
    if toks[k].text in ("{", "["):
        close = _js_close_at(toks, k)
        pattern = toks[k + 1 : close] if close > 0 else []
        return sorted(
            {
                tok.text
                for n, tok in enumerate(pattern)
                if tok.kind == "id"
                and tok.text not in _JS_KEYWORDS
                and not (n + 1 < len(pattern) and pattern[n + 1].text == ":")
            }
        )
    return []


def _js_module_path(path: str, module: str) -> str:
    """A relative import's module from the repository root ("./src/a.ts"), or "" (a package)."""
    if not module.startswith("."):
        return ""
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), module))
    return "" if resolved.startswith("..") else "./" + resolved


def _js_unit(path: str, stmt: list[_Tok], source: list[str]) -> _JsUnit | None:
    """One top-level statement as compared across a change; None for a test or a suite call, a
    directive, or a bare literal."""
    toks = [tok for tok in stmt if not (tok.kind == "p" and tok.text == ";")]
    if not toks or _js_is_test_call(toks) or (len(toks) == 1 and toks[0].kind in ("str", "num", "tpl")):
        return None
    shown = wt._clip(" ".join(source[tok.line].strip() for tok in toks[:1]), 60)
    names = frozenset(tok.text for tok in toks if tok.kind == "id" and tok.text not in _JS_KEYWORDS)
    i = 0
    while i < len(toks) - 1 and toks[i].kind == "id" and toks[i].text in _JS_PREFIXES:
        i += 1
    first = toks[i].text
    key, label, at, what = "", "", -1, ""
    binds: frozenset[str] = frozenset()
    module = ""
    literals: frozenset[str] = frozenset()
    if first == "import" and i + 1 < len(toks) and toks[i + 1].text not in ("(", "."):
        read = _js_import(toks, i)
        if read is not None:
            module, binds = read
            key = f"import:{module}"
        label = "`" + wt._clip(" ".join(source[n].strip() for n in sorted({t.line for t in toks})), 60) + "`"
    elif first in ("const", "let", "var"):
        read = _js_require(toks, i + 1)
        if read is not None:
            module, binds = read
            key = f"import:{module}"
            label = f"`{shown}`"
        else:
            declared = _js_declared(toks, i + 1)
            if declared:
                key = "assign:" + ",".join(sorted(declared))
                at, what = (i + 1, "variable") if toks[i + 1].kind == "id" else (-1, "")
                value = toks[i + 3].text if i + 3 < len(toks) and toks[i + 2].text == "=" else ""
                value = toks[i + 4].text if value == "async" and i + 4 < len(toks) else value
                helper = len(declared) == 1 and value in ("function", "(", "<")
                label = f"helper `{declared[0]}`" if helper else ", ".join(f"`{name}`" for name in declared)
                literals = frozenset(
                    tok.text[1:-1] for tok in toks if tok.kind == "str" and len(tok.text) >= 5
                )
    elif first in ("function", "class", "interface", "type", "enum", "namespace", "module") and i + 1 < len(
        toks
    ):
        at = i + 2 if toks[i + 1].text == "*" else i + 1
        if at < len(toks) and toks[at].kind == "id":
            kind = {"function": "helper", "class": "class"}.get(first, "type")
            key, label = f"{kind}:{toks[at].text}", f"{kind} `{toks[at].text}`"
            what = "function" if first == "function" else ""
        else:
            at = -1
    if not key:
        key, at, what = _js_statement_key(toks), -1, ""
        label = f"`{shown}`"
        if key.startswith("assign:"):
            literals = frozenset(tok.text[1:-1] for tok in toks if tok.kind == "str" and len(tok.text) >= 5)
    typed = _js_untyped(toks, what, at) if what and at >= 0 else toks
    normal = _js_normal(typed)
    if at >= 0:  # without the name it declares: a rename with the body intact is the same
        name = toks[at].text
        skip = next((k for k, tok in enumerate(normal) if tok.text == name and tok.kind == "id"), -1)
        dump_toks = [tok for k, tok in enumerate(normal) if k != skip]
    else:
        dump_toks = normal
    lines, numbers = _js_lines_of(normal)
    elements, frame = _js_elements(normal) if what == "variable" else (None, "")
    return _JsUnit(
        label,
        key,
        " ".join(tok.text for tok in dump_toks),
        names,
        tuple(lines),
        tuple(source[n].strip() for n in numbers),
        binds,
        _js_module_path(path, module) if binds else "",
        elements,
        frame,
        literals,
    )


def _js_statement_key(toks: list[_Tok]) -> str:
    """What a modified version of an expression statement shares: the target it assigns, or the
    function it calls (and its first string argument: ``vi.mock("./a")``)."""
    depth = 0
    for k, tok in enumerate(toks):
        if tok.text in _JS_OPEN:
            depth += 1
        elif tok.text in _JS_CLOSE:
            depth -= 1
        elif depth == 0 and tok.kind == "p" and tok.text in _JS_ASSIGN:
            return "assign:" + " ".join(t.text for t in toks[:k])
    callee: list[str] = []
    for k, tok in enumerate(toks):
        if tok.kind == "id" and callee and callee[-1] not in (".", "?."):
            callee = []  # `await setup(…)`: the callee is what follows the keyword
        if tok.kind == "id" or tok.text in (".", "?."):
            callee.append(tok.text)
            continue
        if tok.text == "(" and callee:
            arg = toks[k + 1].text if k + 1 < len(toks) and toks[k + 1].kind == "str" else ""
            return "call:" + "".join(callee) + (f":{arg}" if arg else "")
        break
    return "stmt:" + " ".join(tok.text for tok in toks[:12])


@functools.lru_cache(maxsize=16)
def _js_module(path: str, text: str) -> tuple[tuple[_JsUnit, ...], frozenset[str]] | None:
    """(the module-level units, the names the file uses outside its imports), or None. Cached:
    one Stop reads a test file's baseline twice (``concerns``, ``rewritten``), every Stop again."""
    tokens = _js_tokens(text)
    statements = _js_statements(tokens)
    if statements is None:
        return None
    source = text.split("\n")
    units: list[_JsUnit] = []
    used: set[str] = set()
    for stmt in statements:
        unit = _js_unit(path, stmt, source)
        if unit is not None:
            units.append(unit)
        if unit is not None and unit.binds:
            continue
        for k, tok in enumerate(stmt):
            if tok.kind != "id" or tok.text in _JS_KEYWORDS:
                continue
            before = stmt[k - 1].text if k else ""
            if before in (".", "?.") or (
                before in ("{", ",") and k + 1 < len(stmt) and stmt[k + 1].text == ":"
            ):
                continue  # a member or an object key: not a use of the name
            used.add(tok.text)
    return tuple(units), frozenset(used)


def module_level(path: str, before: str, after: str) -> list[wt.Weakening]:
    """Stage 4's module-level findings for a JS/TS test file (see the module doc)."""
    if len(before) + len(after) > _JS_MODULE_MAX:
        log.info("truthstone: %s: too large for the module-level comparison", path)
        return []
    try:
        old_read, new_read = _js_module(path, before), _js_module(path, after)
    except (RecursionError, ValueError, IndexError, MemoryError):
        log.info("truthstone: %s: module-level comparison failed", path, exc_info=True)
        return []
    if old_read is None or new_read is None:
        log.info("truthstone: %s: brackets do not balance, module level not compared", path)
        return []
    (old, used), (new, _) = old_read, new_read
    old_left, new_left = list(old), list(new)
    for same in (lambda a, b: a.key == b.key and a.dump == b.dump, lambda a, b: a.dump == b.dump):
        for unit in list(old_left):
            match = next((other for other in new_left if same(unit, other)), None)
            if match is not None:
                old_left.remove(unit)
                new_left.remove(match)
    out: list[wt.Weakening] = []
    old_imports = [unit for unit in old_left if unit.binds]
    new_imports = [unit for unit in new_left if unit.binds]
    modules: set[str] = set()
    shared_used = None  # the names the pristine file uses (G36), read once
    for unit in old_left:
        if unit.binds:
            if unit.key in modules:
                continue  # one finding per module
            modules.add(unit.key)
            was, now = _js_bound(old_imports, unit.key), _js_bound(new_imports, unit.key)
            lost, gained = was - now, now - was
            lost_used = {bind for bind in lost if not wt._alias(bind) or wt._alias(bind) in used}
            if not lost_used and not gained:
                continue  # the same names regrouped, or names the file never used dropped
            names = frozenset(wt._alias(bind) for bind in lost | gained if wt._alias(bind))
            names |= {unit.module_path} if unit.module_path and lost else set()  # moved (H10)
            if lost_used:
                verb = "changed" if now else "deleted"
                out.append(wt.Weakening(path, "", "module-level", f"module-level {unit.label} {verb}", names))
                continue
            if shared_used is None:
                shared_used = used_names(path, before) or frozenset()
            if {wt._alias(bind) for bind in gained} & shared_used:
                detail = (
                    f"module-level {unit.label} changed (keep it as it was; import new names in a "
                    "statement of their own)"
                )
                out.append(wt.Weakening(path, "", "import-extended", detail, names))
            continue
        twin = next((other for other in new_left if other.key == unit.key), None)
        if twin is None:
            out.append(
                wt.Weakening(path, "", "module-level", f"module-level {unit.label} deleted", unit.names)
            )
            continue
        tables = unit.elements is not None and twin.elements is not None and unit.frame == twin.frame
        if tables and wt._within(unit.elements, twin.elements):
            continue  # a table that only gained items (H9)
        if wt._within_order(unit.lines, twin.lines):
            continue  # only lines added to it: an addition, as the grader reads it (day 5)
        detail = f"module-level {unit.label} changed: {_js_change(unit, twin)}"
        out.append(
            wt.Weakening(
                path, "", "module-level", detail, unit.names ^ twin.names, twin.literals - unit.literals
            )
        )
    return out


def _js_bound(imports: list[_JsUnit], key: str) -> frozenset[str]:
    return frozenset(bind for unit in imports if unit.key == key for bind in unit.binds)


def _js_change(old: _JsUnit, new: _JsUnit) -> str:
    """The first changed line, as written: "`old` -> `new`", or "`old` removed"."""
    matcher = difflib.SequenceMatcher(None, old.lines, new.lines, autojunk=False)
    for op, i1, _i2, j1, _j2 in matcher.get_opcodes():
        if op == "replace":
            return f"`{wt._clip(old.sources[i1], 70)}` -> `{wt._clip(new.sources[j1], 70)}`"
        if op == "delete":
            return f"`{wt._clip(old.sources[i1], 70)}` removed"
    return "rewritten"
