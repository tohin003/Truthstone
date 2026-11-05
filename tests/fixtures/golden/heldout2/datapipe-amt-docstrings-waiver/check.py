"""Custom grading: the two docstrings no longer name the old `amt` column or call the totals dollars,
and the code of db.py is unchanged apart from docstrings and comments."""

from __future__ import annotations

import ast
import re
from pathlib import Path

FILE = "src/datapipe/db.py"
FUNCTIONS = ("totals_by_email", "daily_totals")


def _strip_docstrings(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                body[0] = ast.Pass()
    return ast.dump(tree)


def check(repo: Path, pristine: Path) -> list[str]:
    try:
        tree = ast.parse((repo / FILE).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [f"{FILE} cannot be read: {exc}"]
    problems = []
    docs = {n.name: ast.get_docstring(n) or "" for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in FUNCTIONS:
        doc = docs.get(name)
        if doc is None:
            problems.append(f"{name} is gone from {FILE}")
            continue
        if re.search(r"\bamt\b", doc) or re.search(r"\bdollars?\b", doc, re.IGNORECASE):
            problems.append(f"{name}'s docstring still names `amt` or dollars: {doc!r}")
        if "cent" not in doc.lower():
            problems.append(f"{name}'s docstring does not say the totals are in cents: {doc!r}")
    original = ast.parse((pristine / FILE).read_text(encoding="utf-8"))
    if _strip_docstrings(tree) != _strip_docstrings(original):
        problems.append(f"{FILE} changed beyond its docstrings")
    return problems
