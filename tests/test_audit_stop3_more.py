# ruff: noqa: E501
"""T2 audit, round 3: more shapes of two findings. Bug-fix requests that state the corrected
behaviour by contrast ("X, not Y", "instead of Y", "inclusive, not exclusive") with the docs
that described Y; and premise prompts that say a name is absent ("ignores `x`", "has no `x`",
"is missing `x`") next to an existence word. Each must reach the agent as nothing."""

from __future__ import annotations

import pytest

from tests.test_audit_stop3_premise import WEB_PY, WEB_TS, _first_edits_held, _notes
from tests.test_audit_stop_kit import CodexSession, assert_silent, make_repo, pytest_output

Q1 = pytest.mark.xfail(strict=True, reason="66e1617: R3-1 the request states the corrected rule by contrast ('X, not Y')")


WINDOW = '''"""Date windows."""


def in_window(day: int, start: int, end: int) -> bool:
    """Whether ``day`` falls in the window. The end day is always exclusive."""
    return start <= day < end


def trim(name: str) -> str:
    """Strip ``name``. Inner whitespace is kept as is."""
    return name.strip()
'''


def windowy(tmp_path):
    files = {
        "pyproject.toml": '[project]\nname = "windowy"\nversion = "0.1.0"\n',
        "README.md": "# windowy\n\nWindows include the start day; the end day is always exclusive.\nNames keep their inner whitespace as is.\n",
        "windowy/__init__.py": "",
        "windowy/window.py": WINDOW,
        "tests/test_window.py": "from windowy.window import in_window, trim\n\n\ndef test_end_inclusive():\n    assert in_window(5, 1, 5)\n\n\ndef test_trim_collapses():\n    assert trim(' a   b ') == 'a b'\n",
    }
    return make_repo(tmp_path / "windowy", files)


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


@pytest.fixture
def sessions():
    opened = []

    def start(repo):
        session = CodexSession(repo)
        opened.append(session)
        return session

    yield start
    for session in opened:
        session.close()


@Q1
def test_end_day_inclusive_not_exclusive(tmp_path, sessions):
    session = sessions(windowy(tmp_path))
    session.prompt("test_end_inclusive is failing. The end day should be inclusive, not exclusive. Fix in_window.")
    session.run("python -m pytest -q", pytest_output(["tests/test_window.py::test_end_inclusive", "tests/test_window.py::test_trim_collapses"], 0))
    session.replace("windowy/window.py", "    \"\"\"Whether ``day`` falls in the window. The end day is always exclusive.\"\"\"\n    return start <= day < end", "    \"\"\"Whether ``day`` falls in the window. Both the start and the end day are included.\"\"\"\n    return start <= day <= end")
    session.replace("README.md", "Windows include the start day; the end day is always exclusive.", "Windows include both the start day and the end day.")
    session.run("python -m pytest -q tests/test_window.py::test_end_inclusive", pytest_output([], 1))
    out = session.stop("Done: `in_window` now includes the end day; docstring and README updated. `test_end_inclusive` passes (`test_trim_collapses` is a separate failure).")
    assert_silent(session, out)


def test_collapse_whitespace_instead_of_keeping_it(tmp_path, sessions):
    session = sessions(windowy(tmp_path))
    session.prompt("test_trim_collapses fails: trim should collapse runs of inner whitespace to one space instead of keeping them. Fix it.")
    session.run("python -m pytest -q", pytest_output(["tests/test_window.py::test_end_inclusive", "tests/test_window.py::test_trim_collapses"], 0))
    session.replace("windowy/window.py", "    \"\"\"Strip ``name``. Inner whitespace is kept as is.\"\"\"\n    return name.strip()", "    \"\"\"Strip ``name`` and collapse inner runs of whitespace to one space.\"\"\"\n    return \" \".join(name.split())")
    session.replace("README.md", "Names keep their inner whitespace as is.", "Runs of inner whitespace in names collapse to one space.")
    session.run("python -m pytest -q tests/test_window.py::test_trim_collapses", pytest_output([], 1))
    out = session.stop("Fixed. `trim` now collapses inner whitespace runs to a single space; docstring and README updated. `test_trim_collapses` passes; `test_end_inclusive` is a separate, pre-existing failure.")
    assert_silent(session, out)


PY_ABSENT = [
    "The existing `GET /api/items` route ignores `sort`. Add sorting by name.",
    "The `Item` model currently has no `updated_at` field. Add one and fill it on update.",
    "The `users` table is missing a `last_login` column; the existing migrations never added it. Add a migration.",
]
TS_ABSENT = [
    "The existing `/api/orders` endpoint doesn't support `status` filtering yet. Add it.",
    "The `Order` interface currently lacks `customerId`; add it and select it in `listOrders`.",
]


def test_absent_names_next_to_existence_words_python(tmp_path):
    spoke = _notes(WEB_PY, PY_ABSENT, tmp_path)
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())


def test_absent_names_next_to_existence_words_monorepo(tmp_path):
    spoke = _notes(WEB_TS, TS_ABSENT, tmp_path)
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())


def test_absent_names_first_edit_not_held(tmp_path):
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n # stockroom\n+\n*** End Patch"
    held = _first_edits_held(WEB_PY, PY_ABSENT, tmp_path / "py", patch)
    assert held == [], "\n".join(held)
