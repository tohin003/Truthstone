"""Custom grading: the docs and the QA data no longer use the old field name."""

from __future__ import annotations

from pathlib import Path


def check(repo: Path, pristine: Path) -> list[str]:
    problems = []
    for path in [repo / "README.md", *sorted((repo / "qa").glob("*"))]:
        if path.is_file() and "userId" in path.read_text(encoding="utf-8"):
            problems.append(f"{path.relative_to(repo)} still uses userId")
    return problems
