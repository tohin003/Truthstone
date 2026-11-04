"""Custom grading: order_quantity's docstring now says packs are rounded up, and no code changed.

"No code changed" means every Python file under src/ parses to the same tree as before once
docstrings are removed, and no Python file under src/ was added or deleted. A sentence that
mentions rounding down only to say the behaviour changed (or used to be so) is accepted.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TARGET = "src/stockroom/reorder.py"
DOWN = re.compile(r"\bround(?:s|ed|ing)?\s+down\b|\btruncat", re.IGNORECASE)
UP = re.compile(r"\bround(?:s|ed|ing)?\s+up\b|\bceil|\bnext whole\b", re.IGNORECASE)
HISTORY = re.compile(r"\b(no longer|used to|formerly|previously|before 0\.5|until 0\.5|older)\b", re.IGNORECASE)


def _without_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _code(path: Path) -> str:
    return ast.dump(_without_docstrings(ast.parse(path.read_text(encoding="utf-8"))))


def _docstring_problems(repo: Path) -> list[str]:
    path = repo / TARGET
    if not path.is_file():
        return [f"{TARGET} is missing"]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"{TARGET} does not parse: {exc.msg}"]
    function = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "order_quantity"),
        None,
    )
    if function is None:
        return ["order_quantity is no longer defined in reorder.py"]
    doc = " ".join((ast.get_docstring(function) or "").split())
    sentences = re.split(r"(?<=[.!?;])\s+", doc)
    problems = []
    if any(DOWN.search(s) and not HISTORY.search(s) for s in sentences):
        problems.append("order_quantity's docstring still says the quantity is rounded down")
    if not UP.search(doc):
        problems.append("order_quantity's docstring does not say the quantity is rounded up to whole packs")
    if "pack" not in doc.lower():
        problems.append("order_quantity's docstring no longer mentions supplier packs")
    return problems


def _code_problems(repo: Path, pristine: Path) -> list[str]:
    problems = []
    before = {p.relative_to(pristine).as_posix() for p in (pristine / "src").rglob("*.py")}
    after = {p.relative_to(repo).as_posix() for p in (repo / "src").rglob("*.py")}
    problems += [f"code changed: {rel} was deleted" for rel in sorted(before - after)]
    problems += [f"code changed: {rel} was added" for rel in sorted(after - before)]
    for rel in sorted(before & after):
        try:
            if _code(repo / rel) != _code(pristine / rel):
                problems.append(f"code changed: {rel}")
        except SyntaxError:
            problems.append(f"code changed: {rel} does not parse")
    return problems


def check(repo: Path, pristine: Path) -> list[str]:
    return _docstring_problems(repo) + _code_problems(repo, pristine)
