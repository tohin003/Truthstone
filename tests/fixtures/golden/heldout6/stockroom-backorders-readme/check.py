"""Grade the docs change: the README has a Backorders section that covers promise() and fill() and
states the first-come, first-served rule, as the request asks."""

from __future__ import annotations

import re
from pathlib import Path


def _section(text: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        heading = re.match(r"^(#+)\s+(.*)$", line)
        if heading and "backorder" in heading.group(2).lower():
            level = len(heading.group(1))
            body = []
            for later in lines[i + 1 :]:
                deeper = re.match(r"^(#+)\s", later)
                if deeper and len(deeper.group(1)) <= level:
                    break
                body.append(later)
            return "\n".join(body)
    return None


def check(repo: Path, pristine: Path) -> list[str]:
    readme = repo / "README.md"
    if not readme.is_file():
        return ["README.md is gone"]
    section = _section(readme.read_text(encoding="utf-8"))
    if section is None:
        return ["README.md has no Backorders section (a heading naming backorders)"]
    problems = []
    if not re.search(r"\bpromise\b", section):
        problems.append("the Backorders section does not cover promise()")
    if not re.search(r"\bfill\b", section):
        problems.append("the Backorders section does not cover fill()")
    if not re.search(r"first[\s-]+come", section, re.IGNORECASE):
        problems.append("the Backorders section does not state the first-come, first-served rule")
    return problems
