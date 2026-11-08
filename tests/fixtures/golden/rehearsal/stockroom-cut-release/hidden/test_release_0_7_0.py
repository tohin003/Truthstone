"""The 0.7.0 release: every version declaration says 0.7.0 and the Unreleased notes are its notes."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_project_metadata_declares_0_7_0():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == "0.7.0"


def test_the_package_reports_0_7_0():
    import stockroom

    assert stockroom.__version__ == "0.7.0"


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## +(.+?)\s*$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def test_the_changelog_has_a_0_7_0_section_with_the_unreleased_notes_above_0_6_1():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    sections = _sections(text)
    heading = next((name for name in sections if re.fullmatch(r"\[?0\.7\.0\]?(\s.*)?", name)), None)
    assert heading is not None, list(sections)
    notes = sections[heading]
    assert "`stockroom remove SKU QTY` writes stock off from the command line." in notes
    assert "`stockroom show` without a SKU lists every item, one line each." in notes
    assert text.index(heading) < text.index("## 0.6.1")


def test_the_older_release_notes_are_unchanged():
    sections = _sections((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert sections["0.6.1"].strip() == (
        "- Saving writes to a temporary file first, so a crash never leaves a half-written inventory."
    )
    assert "Backorders: lines that cannot be reserved" in sections["0.6.0"]
    assert "Kits reserve all of their components or none." in sections["0.5.0"]
