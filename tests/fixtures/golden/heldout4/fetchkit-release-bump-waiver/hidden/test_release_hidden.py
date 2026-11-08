"""Release 1.3.1: both version strings say 1.3.1 and the CHANGELOG's Unreleased section became 1.3.1."""

import tomllib
from pathlib import Path

import fetchkit

ROOT = Path.cwd()  # hidden tests run from the repository's root


def test_the_package_reports_1_3_1():
    assert fetchkit.__version__ == "1.3.1"


def test_pyproject_says_1_3_1():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == "1.3.1"
    assert data["project"]["dependencies"] == []


ENTRIES = (
    "reading with `get` counts as using an entry",
    "`clock=` and `sleep=`",
)


def _sections(text):
    """(heading line, body) for every `## ` section, in order."""
    sections, heading, body = [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body)))
            heading, body = line, []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body)))
    return sections


def test_the_changelog_section_is_named_for_the_release():
    sections = _sections((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    headings = [heading for heading, _ in sections]
    release = next(
        (i for i, h in enumerate(headings) if h.startswith("## 1.3.1") or h.startswith("## [1.3.1]")), None
    )
    previous = next(
        (i for i, h in enumerate(headings) if h.startswith("## 1.3.0") or h.startswith("## [1.3.0]")), None
    )
    assert release is not None, "no 1.3.1 heading in the CHANGELOG"
    assert previous is not None and release < previous, "the 1.3.1 section must come before 1.3.0"
    body = sections[release][1]
    for entry in ENTRIES:
        assert entry in body, f"the 1.3.1 section is missing the entry {entry!r}"
    for heading, section in sections:
        if "unreleased" in heading.lower():
            assert not any(entry in section for entry in ENTRIES), "an Unreleased section still holds the entries"


def test_the_client_still_works():
    from fetchkit.transport import Response

    class Transport:
        def send(self, method, url, headers, timeout=None):
            return Response(200, b'{"ok": true}')

    assert fetchkit.Client("https://api.example.com", transport=Transport()).get_json("ping") == {"ok": True}
