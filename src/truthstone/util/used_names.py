"""The names a file USES: one helper for the bench grader (G36) and the product.

Ported from the frozen prototype ``g36_proto_v3.py`` (``js_code``, ``used_names``; appendix
RULES-G36-v3 §1). Standard library only, and it imports nothing else from ``truthstone``: the
bench grader (``bench/codex/testedits.py``) loads it, so the grader loads no product code, and
the product's retirement of unused ``import-extended`` items (``validate/weakened_tests.py``)
reads the same set.

A name is *used* by a file when it appears in it as follows.

* **Python** (``.py``, ``.pyi``): an ``ast.Name`` id, or a name an import binds (the alias, or
  the first part of a dotted ``import a.b``, which binds ``a``). Attribute names (``x.Name``)
  never count. A file that does not parse has no set (None).
* **TS/JS** (``.ts .tsx .mts .cts .js .jsx .mjs .cjs``): an identifier in the code, read with
  comments removed and string literals blanked; template-literal text is blanked but its
  ``${...}`` expressions stay code, and a spread ``...x`` counts. Two cases do not count: an
  identifier directly after ``.`` or ``?.`` (a member access), and an object-literal key (an
  identifier followed by ``:`` whose previous code character is ``{`` or ``,``). An import
  statement's own remote names are identifiers in code too (``a`` in ``import { a as b }``),
  where Python has only the bound alias.
* **Other files:** None.
"""

from __future__ import annotations

import ast
import re

_PY_EXT = (".py", ".pyi")
_JS_EXT = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

# -- a TS/JS code view: comments removed, string literals blanked, newlines kept ----------------------

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


_IDENT_RE = re.compile(r"(?<![\w$])[A-Za-z_$][\w$]*")


def used_names(path: str, text: str | None) -> frozenset[str] | None:
    """The names a file USES (see the module docstring); None when unknown."""
    if text is None:
        return None
    lower = path.lower()
    if lower.endswith(_PY_EXT):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return None
        out: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                out.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    out.add(alias.asname or alias.name.split(".")[0])
        return frozenset(out)
    if lower.endswith(_JS_EXT):
        code = js_code(text)
        out = set()
        for m in _IDENT_RE.finditer(code):
            j = m.start() - 1
            while j >= 0 and code[j] in " \t\r\n":
                j -= 1
            prev = code[j] if j >= 0 else ""
            if prev == "." and not (j >= 2 and code[j - 2 : j + 1] == "..."):
                continue  # a member access: x.Name, x?.Name (a spread ...Name is a use)
            k = m.end()
            while k < len(code) and code[k] in " \t\r\n":
                k += 1
            if k < len(code) and code[k] == ":" and prev in ("{", ",") and code[k + 1 : k + 2] != ":":
                continue  # an object-literal key
            out.add(m.group(0))
        return frozenset(out)
    return None
