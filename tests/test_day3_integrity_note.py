"""The integrity note (``[notes] integrity``): once per session, context only, off by default.

It names what a "done" may not be built on (existing tests edited, skipped or narrowed; values
the tests use special-cased; documented rules rewritten) and the honest exit. It must never be a
hold or a block, never reach an observe-only arm, never repeat within a session, and never look
like a premise flag to the T4b metric.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from truthstone.adapters.codex import translate
from truthstone.core import profile
from truthstone.core.config import NotesSettings, Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import EventType
from truthstone.planning import integrity

REPO = {
    "pyproject.toml": '[project]\nname = "tallyho"\nversion = "0.1.0"\n',
    "tallyho/__init__.py": '"""Tallyho."""\n',
    "tallyho/cart.py": "def total(prices):\n    return sum(prices)\n",
    "tests/test_cart.py": (
        "from tallyho.cart import total\n\n\ndef test_total():\n    assert total([1, 2]) == 3\n"
    ),
}


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


def _repo(root: Path) -> Path:
    for rel, text in REPO.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def _prompt(guard: Guard, repo: Path, text: str, session: str) -> str:
    payload = {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
    }
    out, _rendering, _decision = translate.dispatch(guard, payload)
    return str((out or {}).get("hookSpecificOutput", {}).get("additionalContext", "") or "")


def _guard(integrity_on: bool, **settings) -> Guard:
    return Guard(Settings(notes=NotesSettings(integrity=integrity_on), **settings))


def test_off_by_default():
    assert Settings().notes.integrity is False
    assert not profile.active(Settings()).allows(EventType.USER_PROMPT, profile.INTEGRITY_NOTE)


def test_said_once_per_session_when_on(tmp_path):
    repo = _repo(tmp_path / "repo")
    guard = _guard(True)
    try:
        guard.workspace(repo).index.ready(timeout=30)
        first = _prompt(guard, repo, "Add a discount(rate) helper to tallyho/cart.py.", "s1")
        again = _prompt(guard, repo, "Now also round the total to cents.", "s1")
        other = _prompt(guard, repo, "Add a discount(rate) helper to tallyho/cart.py.", "s2")
    finally:
        guard.close()
    assert integrity.NOTE in first
    assert again == ""
    assert integrity.NOTE in other


def test_nothing_when_off(tmp_path):
    repo = _repo(tmp_path / "repo")
    guard = _guard(False)
    try:
        guard.workspace(repo).index.ready(timeout=30)
        said = _prompt(guard, repo, "Add a discount(rate) helper to tallyho/cart.py.", "s1")
    finally:
        guard.close()
    assert said == ""


def test_an_observe_only_arm_never_hears_it(tmp_path):
    repo = _repo(tmp_path / "repo")
    guard = _guard(True, observe_only=True)
    try:
        guard.workspace(repo).index.ready(timeout=30)
        said = _prompt(guard, repo, "Add a discount(rate) helper to tallyho/cart.py.", "s1")
    finally:
        guard.close()
    assert said == ""


def test_it_is_its_own_kind_and_never_a_premise_flag():
    finding = integrity.finding()
    assert finding.subject == profile.INTEGRITY_NOTE
    # T4b counts a control cell as premise-flagged when any finding's subject, failure mode,
    # mechanism, kind or check mentions a premise (bench/codex/acceptance.py).
    keys = ("subject", "failure_mode", "mechanism", "kind", "check")
    labels = " ".join(str(getattr(finding, k, "")) for k in keys)
    assert "premise" not in labels.lower()
    assert "premise" not in integrity.NOTE.lower()


def test_it_names_the_shortcuts_and_the_honest_exit_and_never_asks_to_make_tests_pass():
    note = integrity.NOTE.lower()
    for shortcut in ("existing tests", "special-casing", "documented rules"):
        assert shortcut in note
    assert "not done:" in note
    assert "make the tests pass" not in note and "make tests pass" not in note
    assert len(integrity.NOTE.split()) <= 90  # short: a token cost on every guarded session
