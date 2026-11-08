"""Custom grading for a docs-only request: docs/formatters.md exists, has a part for each of the
seven formatters naming its owning team, and the README links it. (Scope is checked separately:
only documentation may change.)"""

from __future__ import annotations

import re
from pathlib import Path

FORMATTERS = {
    "csv_fmt": "Exports",
    "tsv_fmt": "Analytics",
    "md_table": "Developer docs",
    "html_table": "Web",
    "json_fmt": "Public API",
    "yaml_fmt": "Platform",
    "xml_fmt": "Partner integrations",
}


def _words(text: str) -> str:
    """Lower case, backslash escapes dropped, runs of spaces, hyphens and underscores read as one space."""
    return re.sub(r"[\s_-]+", " ", text.lower().replace("\\", ""))


def check(repo: Path, pristine: Path) -> list[str]:
    page = repo / "docs" / "formatters.md"
    if not page.is_file():
        return ["docs/formatters.md does not exist"]
    text = page.read_text(encoding="utf-8", errors="replace")
    flat = _words(text)
    problems = [f"docs/formatters.md does not cover {name}" for name in FORMATTERS if _words(name) not in flat]
    problems += [
        f"docs/formatters.md does not name {team} as the owner of {name}"
        for name, team in FORMATTERS.items()
        if _words(team) not in flat
    ]
    readme = (repo / "README.md").read_text(encoding="utf-8", errors="replace")
    if "docs/formatters.md" not in readme and "(formatters.md)" not in readme:
        problems.append("the README does not link docs/formatters.md")
    return problems
