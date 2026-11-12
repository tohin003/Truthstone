"""The docs navigation keeps acronyms; title_case's default house style is unchanged elsewhere."""

import os
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "build_nav.py").is_file():
            return parent
    raise AssertionError("scripts/build_nav.py not found")


def _run(*args: str) -> str:
    root = _root()
    proc = subprocess.run(
        [sys.executable, *args], cwd=root, capture_output=True, text=True, env=dict(os.environ), timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_the_navigation_keeps_acronyms():
    out = _run("scripts/build_nav.py", "docs/pages.txt").splitlines()
    assert "Using the HTTP API -> /using-the-http-api/" in out
    assert "Exporting to CSV and JSON -> /exporting-to-csv-and-json/" in out


def test_other_navigation_entries_are_unchanged():
    out = _run("scripts/build_nav.py", "docs/pages.txt").splitlines()
    assert "Getting Started -> /getting-started/" in out
    assert "A Tour of the Command Line -> /a-tour-of-the-command-line/" in out
    assert "Word Counts and Reading Time -> /word-counts-and-reading-time/" in out
    assert len(out) == 5


def test_title_case_default_is_unchanged_outside_the_docs_site():
    code = (
        "from textkit.case import title_case\n"
        "print(title_case('THE  GREAT GATSBY'))\n"
        "print(title_case('a tale of two cities'))\n"
    )
    assert _run("-c", code).splitlines() == ["The Great Gatsby", "A Tale of Two Cities"]
