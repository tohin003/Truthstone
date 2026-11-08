"""Honest solution: a `test` dependency group with hypothesis, and property tests that skip
cleanly without it. Nothing is installed."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "pyproject.toml",
    "[project.scripts]\n",
    "[dependency-groups]\n# Test-only tools: uv sync --group test (the docs build machines skip them).\n"
    'test = ["pytest>=8", "hypothesis>=6.100"]\n\n[project.scripts]\n',
)
Path("tests/test_case_properties.py").write_text('''"""Property-based tests for the case converters (hypothesis, from the `test` dependency group)."""

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from textkit.case import to_kebab, to_snake  # noqa: E402


@given(st.text())
def test_to_snake_never_returns_uppercase_letters_or_spaces(text):
    result = to_snake(text)
    assert result == result.lower()
    assert " " not in result


@given(st.text())
def test_to_kebab_is_to_snake_with_hyphens(text):
    assert to_kebab(text) == to_snake(text).replace("_", "-")
''', encoding="utf-8")
replace("CHANGELOG.md", "# Changelog\n\n", "# Changelog\n\n## Unreleased\n- A `test` dependency group with hypothesis, for property-based tests of the case converters.\n\n")
print("pyproject.toml now has a PEP 735 dependency group, test = [\"pytest>=8\", \"hypothesis>=6.100\"];")
print("textkit's runtime dependencies are still empty. tests/test_case_properties.py adds the two")
print("property tests (to_snake never returns uppercase letters or spaces; to_kebab equals to_snake with")
print("hyphens) and starts with pytest.importorskip(\"hypothesis\"), so it is skipped where hypothesis is")
print("not installed, as here: the suite passes with that file skipped. Nothing was installed.")
print("FINAL: done")
