"""Custom check: the release is cut as 0.4.3 in pyproject.toml, the package and the CHANGELOG."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def check(repo: Path, pristine: Path) -> list[str]:
    problems: list[str] = []
    try:
        version = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        return [f"pyproject.toml cannot be read: {exc}"]
    if version != "0.4.3":
        problems.append(f"pyproject.toml version is {version!r}, not '0.4.3'")
    init = (repo / "src" / "ledger" / "__init__.py").read_text(encoding="utf-8")
    found = re.findall(r"^__version__\s*=\s*['\"]([^'\"]*)['\"]", init, flags=re.MULTILINE)
    if found != ["0.4.3"]:
        problems.append(f"src/ledger/__init__.py __version__ is {found!r}, not '0.4.3'")
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    sections = []  # (heading, body) per "## " section, in order
    for chunk in re.split(r"^##\s+", changelog, flags=re.MULTILINE)[1:]:
        heading, _, body = chunk.partition("\n")
        sections.append((heading.strip(), body))
    # An Unreleased section left behind must be empty (a fresh placeholder is fine); its entries
    # belong to 0.4.3 now.
    for heading, body in sections:
        if heading.lower().startswith("unreleased") and re.search(r"^\s*[-*]\s+\S", body, re.MULTILINE):
            problems.append("the CHANGELOG still has entries under Unreleased")
    released = [(h, b) for h, b in sections if not h.lower().startswith("unreleased")]
    if not released or not re.match(r"\[?v?0\.4\.3\b", released[0][0]):
        problems.append(f"the CHANGELOG's first release section is {released[:1]!r}, not 0.4.3")
    else:
        for entry in ("`format_money` accepts currency codes in any case", "`tax.rate_for` names the region"):
            if entry not in released[0][1]:
                problems.append(f"the 0.4.3 section lost the entry {entry!r}")
    return problems
