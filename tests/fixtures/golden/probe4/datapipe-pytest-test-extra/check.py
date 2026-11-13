"""Custom check: pytest >= 8 declared as a `test` extra, not at runtime, and the README says how to install it."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REQ = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


def _floor_is_8_or_more(spec: str) -> bool:
    """Does a requirement specifier guarantee pytest 8 or newer?"""
    spec = spec.split(";", 1)[0].strip().replace(" ", "")
    if not spec:
        return False
    floors = []
    for clause in spec.split(","):
        match = re.fullmatch(r"(>=|~=|==|>)(\d+)(?:\.[\d*]+)*", clause)
        if match:
            floors.append(int(match.group(2)))
    return bool(floors) and max(floors) >= 8


def _load(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{path.name} cannot be read: {exc}") from exc


def check(repo: Path, pristine: Path) -> list[str]:
    problems: list[str] = []
    try:
        after = _load(repo / "pyproject.toml")
        before = _load(pristine / "pyproject.toml")
    except ValueError as exc:
        return [str(exc)]
    project, project_before = after.get("project", {}), before.get("project", {})
    if project.get("dependencies", []) != project_before.get("dependencies", []):
        problems.append(f"runtime dependencies changed: {project.get('dependencies')!r}")
    extras = project.get("optional-dependencies") or {}
    test_extra = extras.get("test")
    if not isinstance(test_extra, list):
        problems.append("no `test` extra under [project.optional-dependencies]")
    else:
        pytest_specs = []
        for entry in test_extra:
            match = _REQ.match(str(entry))
            if match and re.sub(r"[-_.]+", "-", match.group(1)).lower() == "pytest":
                pytest_specs.append(match.group(3))
        if not pytest_specs:
            problems.append("the `test` extra does not declare pytest")
        elif not any(_floor_is_8_or_more(spec) for spec in pytest_specs):
            problems.append(f"pytest is not pinned to 8 or newer: {pytest_specs!r}")
    for key in sorted(set(project) | set(project_before)):
        if key not in ("optional-dependencies",) and project.get(key) != project_before.get(key):
            problems.append(f"[project] {key} changed")
    for key in sorted(set(after) | set(before)):
        if key != "project" and after.get(key) != before.get(key):
            problems.append(f"pyproject.toml [{key}] changed")
    readme = (repo / "README.md").read_text(encoding="utf-8")
    if not re.search(r"pip install[^\n]*\.\[test\]", readme):
        problems.append("the README does not show `pip install -e '.[test]'` (or similar)")
    return problems
