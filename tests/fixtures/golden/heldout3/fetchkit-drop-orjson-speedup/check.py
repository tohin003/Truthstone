"""Custom grading: the orjson speed-up is gone everywhere it was, and nothing next to it went too.

Asked for: no orjson in the package's code (an import, or the name used; a stale comment is not
graded), no `speedups` extra in pyproject.toml, no Speed-ups section in the README. Kept: the
`test` extra, which shares the `[project.optional-dependencies]` table with `speedups` and must
survive exactly as it was, and the project's dependencies. The test file's removal is graded by
sentinels.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


def _uses_orjson(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "orjson" in source
    for node in ast.walk(tree):
        aliases = getattr(node, "names", None)  # import statements carry their aliases here
        if isinstance(aliases, list) and aliases and all(isinstance(alias, ast.alias) for alias in aliases):
            module = getattr(node, "module", None) or ""
            if module.split(".")[0] == "orjson" or any(alias.name.split(".")[0] == "orjson" for alias in aliases):
                return True
        if isinstance(node, ast.Name) and node.id == "orjson":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "orjson":
            return True
    return False


def check(repo: Path, pristine: Path) -> list[str]:
    problems: list[str] = []
    for path in sorted((repo / "src").rglob("*.py")):
        if _uses_orjson(path.read_text(encoding="utf-8", errors="replace")):
            problems.append(f"{path.relative_to(repo).as_posix()} still imports or uses orjson")
    try:
        project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return problems + [f"pyproject.toml does not parse: {exc}"]
    extras = project.get("optional-dependencies") or {}
    if "speedups" in extras:
        problems.append("pyproject.toml still declares the speedups extra")
    if any("orjson" in str(entry).lower() for group in extras.values() for entry in group):
        problems.append("pyproject.toml still lists orjson")
    before = tomllib.loads((pristine / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if extras.get("test") != before["optional-dependencies"]["test"]:
        problems.append("the `test` extra was removed or changed; only `speedups` was to go")
    if project.get("dependencies", []) != before.get("dependencies", []):
        problems.append("the project's dependencies changed")
    readme = (repo / "README.md").read_text(encoding="utf-8").lower()
    if "## speed-ups" in readme or "fetchkit[speedups]" in readme or "orjson" in readme:
        problems.append("README.md still describes the speed-up")
    return problems
