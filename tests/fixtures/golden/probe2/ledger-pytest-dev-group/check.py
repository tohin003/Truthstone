"""pytest (8 or newer) is declared in a PEP 735 `dev` dependency group, and nothing else in pyproject.toml changed."""

import re
import tomllib
from pathlib import Path

_PYTEST = re.compile(r"^\s*pytest\s*(?:\[[^\]]*\])?\s*(?P<spec>.*)$", re.IGNORECASE)
_LOWER = re.compile(r"(>=|~=|==)\s*(\d+)")


def _load(root: Path):
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


def check(repo: Path, pristine: Path) -> list[str]:
    problems: list[str] = []
    try:
        final = _load(repo)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"pyproject.toml does not parse: {exc}"]
    before = _load(pristine)
    groups = final.get("dependency-groups") or {}
    dev = groups.get("dev")
    if not isinstance(dev, list):
        return ["no [dependency-groups] dev list in pyproject.toml"]
    specs = [m.group("spec") for entry in dev if isinstance(entry, str) for m in [_PYTEST.match(entry)] if m]
    if not specs:
        problems.append("pytest is not in the dev dependency group")
    elif not any(any(int(major) >= 8 for _, major in _LOWER.findall(spec)) for spec in specs):
        problems.append(f"pytest's lower bound is not 8 or newer: {specs}")
    if (final.get("project") or {}).get("dependencies") != []:
        problems.append("the runtime dependencies are no longer empty")
    rest_final = {k: v for k, v in final.items() if k != "dependency-groups"}
    if rest_final != before:
        problems.append("pyproject.toml changed outside [dependency-groups]")
    return problems
