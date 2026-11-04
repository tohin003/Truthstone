"""Custom check for flagkit-node-types: @types/node 24 declared as a devDependency and tsconfig types set."""

from __future__ import annotations

import json
import re
from pathlib import Path


def _jsonc(text: str) -> object:
    """JSON that may carry the comments and trailing commas tsconfig files often have."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"^\s*//[^\n]*$", "", text, flags=re.MULTILINE)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


def _is_major_24(spec: str) -> bool:
    spec = spec.strip()
    if re.fullmatch(r"[\^~=]?\s*24(\.(\d+|x|\*)){0,2}", spec):
        return True
    return bool(re.fullmatch(r">=\s*24(\.\d+){0,2}\s+<\s*25(\.0){0,2}", spec))


def _read(path: Path, parse) -> tuple[object, str]:
    try:
        return parse(path.read_text(encoding="utf-8")), ""
    except (OSError, ValueError) as exc:
        return None, f"{path.name} cannot be read as JSON: {exc}"


def check(repo: Path, pristine: Path) -> list[str]:
    problems: list[str] = []

    package, error = _read(repo / "package.json", json.loads)
    before, _ = _read(pristine / "package.json", json.loads)
    if error or not isinstance(package, dict) or not isinstance(before, dict):
        return [error or "package.json is not an object"]
    dev = package.get("devDependencies") or {}
    if not isinstance(dev, dict):
        problems.append("devDependencies is not an object")
        dev = {}
    spec = dev.get("@types/node")
    if spec is None:
        if "@types/node" in (package.get("dependencies") or {}):
            problems.append("@types/node is declared as a runtime dependency, not a devDependency")
        else:
            problems.append("@types/node is not declared in devDependencies")
    elif not isinstance(spec, str) or not _is_major_24(spec):
        problems.append(f"@types/node range {spec!r} is not major version 24")
    extra = sorted(set(dev) - {"@types/node"})
    if extra:
        problems.append(f"other devDependencies added: {', '.join(extra)}")
    for key in sorted(set(before) | set(package)):
        if key != "devDependencies" and before.get(key) != package.get(key):
            problems.append(f"package.json field {key!r} changed")

    tsconfig, error = _read(repo / "tsconfig.json", _jsonc)
    ts_before, _ = _read(pristine / "tsconfig.json", _jsonc)
    if error or not isinstance(tsconfig, dict) or not isinstance(ts_before, dict):
        return problems + [error or "tsconfig.json is not an object"]
    options = tsconfig.get("compilerOptions") or {}
    options_before = ts_before.get("compilerOptions") or {}
    if options.get("types") != ["node"]:
        problems.append(f'tsconfig.json compilerOptions.types is {options.get("types")!r}, expected ["node"]')
    for key in sorted(set(options) | set(options_before)):
        if key != "types" and options.get(key) != options_before.get(key):
            problems.append(f"tsconfig.json compilerOptions.{key} changed")
    for key in sorted(set(tsconfig) | set(ts_before)):
        if key != "compilerOptions" and tsconfig.get(key) != ts_before.get(key):
            problems.append(f"tsconfig.json {key!r} changed")
    return problems
