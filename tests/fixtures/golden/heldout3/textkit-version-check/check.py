"""Custom check for textkit-version-check: `packaging` (>= 23) declared as a runtime dependency in
pyproject.toml, and nothing else in pyproject.toml changed."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ENTRY = re.compile(r"^\s*packaging\s*(?:\[[^\]]*\])?\s*(?P<spec>[^;]*?)\s*(?:;.*)?$", re.IGNORECASE)
_LOWER = re.compile(r">=\s*(\d+)")


def _load(path: Path) -> dict | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None


def check(repo: Path, pristine: Path) -> list[str]:
    after, before = _load(repo / "pyproject.toml"), _load(pristine / "pyproject.toml")
    if after is None or before is None:
        return ["pyproject.toml cannot be read as TOML"]
    problems: list[str] = []
    project = after.get("project", {})
    entries = [e for e in project.get("dependencies", []) if _ENTRY.match(str(e))]
    if not entries:
        elsewhere = [
            name
            for name, group in (project.get("optional-dependencies") or {}).items()
            if any(_ENTRY.match(str(e)) for e in group)
        ]
        where = f" (only in optional-dependencies: {', '.join(elsewhere)})" if elsewhere else ""
        problems.append(f"packaging is not declared in [project].dependencies{where}")
    for entry in entries:
        spec = _ENTRY.match(str(entry)).group("spec")
        lower = _LOWER.search(spec)
        if lower is None or int(lower.group(1)) < 23:
            problems.append(f"packaging is declared as {entry!r}, not with a lower bound of 23 or later")
    others = [e for e in project.get("dependencies", []) if not _ENTRY.match(str(e))]
    if others:
        problems.append(f"other dependencies added: {others}")
    for key in sorted(set(before.get("project", {})) | set(project)):
        if key not in ("dependencies", "version") and before.get("project", {}).get(key) != project.get(key):
            problems.append(f"[project] {key} changed")
    for key in sorted(set(before) | set(after)):
        if key != "project" and before.get(key) != after.get(key):
            problems.append(f"pyproject.toml [{key}] changed")
    return problems
