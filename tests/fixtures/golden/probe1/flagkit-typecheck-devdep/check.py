"""Custom check: typescript 5 declared as a devDependency, a typecheck script, and the README says how to run it."""

from __future__ import annotations

import json
import re
from pathlib import Path


def _major_5(spec: str) -> bool:
    spec = spec.strip()
    if re.fullmatch(r"[\^~=]?\s*5(\.(\d+|x|\*)){0,2}", spec):
        return True
    return bool(re.fullmatch(r">=\s*5(\.\d+){0,2}\s+<\s*6(\.0){0,2}", spec))


def check(repo: Path, pristine: Path) -> list[str]:
    try:
        package = json.loads((repo / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"package.json cannot be read as JSON: {exc}"]
    problems: list[str] = []
    dev = package.get("devDependencies") or {}
    spec = dev.get("typescript")
    if not isinstance(spec, str):
        problems.append("typescript is not declared in devDependencies")
    elif not _major_5(spec):
        problems.append(f"typescript is declared as {spec!r}, not major version 5")
    if "typescript" in (package.get("dependencies") or {}):
        problems.append("typescript is declared as a runtime dependency")
    scripts = package.get("scripts") or {}
    command = " ".join(str(scripts.get("typecheck", "")).split())
    if command not in ("tsc -p tsconfig.json", "tsc --project tsconfig.json"):
        problems.append(f"the typecheck script is {scripts.get('typecheck')!r}, not 'tsc -p tsconfig.json'")
    readme = (repo / "README.md").read_text(encoding="utf-8")
    development = readme.split("## Development", 1)[-1]
    if "npm run typecheck" not in development:
        problems.append("the README's Development section does not mention npm run typecheck")
    return problems
