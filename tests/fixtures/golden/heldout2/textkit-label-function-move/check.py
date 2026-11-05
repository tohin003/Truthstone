"""Custom grading: no reference to the removed function is left in the code, config or README."""

from __future__ import annotations

from pathlib import Path

STALE = ("legacy_case.humanize", '"textkit.legacy_case", "humanize"', "from textkit.legacy_case import humanize")


def check(repo: Path, pristine: Path) -> list[str]:
    problems = []
    files = [repo / "README.md", *sorted((repo / "src").rglob("*.py")), *sorted((repo / "config").rglob("*"))]
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for stale in STALE:
            if stale in text:
                problems.append(f"{path.relative_to(repo)} still refers to {stale}")
    return problems
