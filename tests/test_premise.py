"""False-premise grounding at prompt time (M8): one note when a name the request asserts
exists appears nowhere in the repository; silence on everything else.

Synthetic repositories and made-up names only (ARCHITECTURE-v0.2 §6.2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from truthstone.adapters.codex import translate
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.intent import premise


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


def _repo(root: Path, extra: dict[str, str] | None = None) -> Path:
    repo = root / "acme"
    files = {
        "acme/__init__.py": "",
        "acme/store.py": ("class Store:\n    def take(self, sku, qty):\n        return qty\n"),
        "acme/cli.py": "import argparse\n\nparser = argparse.ArgumentParser()\n",
        "tests/test_store.py": "from acme.store import Store\n\n\ndef test_take():\n    assert Store()\n",
        "service.toml": "[http]\n  max_hops = 5\n",
        ".github/workflows/ci.yml": "jobs:\n  smoke:\n    steps:\n      - run: python -m acme\n",
        "README.md": "# acme\n\nA small store.\n",
        **(extra or {}),
    }
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return repo


def _files(repo: Path) -> list[str]:
    return [p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file()]


def _check(repo: Path, prompt: str) -> premise.Premise:
    return premise.check(prompt, repo, _files(repo))


# -- what is asserted -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt, name",
    [
        (
            "acme already prints every query to stderr when ACME_TRACE=1 is set, so switch that on in CI.",
            "ACME_TRACE",
        ),
        ("acme prints every query when ACME_TRACE=1 is set: turn that on for the smoke job.", "ACME_TRACE"),
        ("Please build it on the existing Store.shift() helper.", "Store.shift()"),
        ("Use the existing `retry_budget` setting for this.", "retry_budget"),
        ("Pass the --dry-run flag when the job syncs.", "--dry-run"),
        ("Sam already wrote the checks in scripts/check_links.py.", "scripts/check_links.py"),
    ],
)
def test_a_name_the_request_asserts_and_nothing_has_is_noted(tmp_path, prompt, name):
    found = _check(_repo(tmp_path), prompt)
    assert [a.name for a in found.missing] == [name]
    assert found.note == (
        f"`{name}` appears nowhere in this repository; the behaviour the request assumes may not exist — "
        "verify before building on it, and tell the user if it doesn't."
    )
    finding = found.finding()
    assert finding is not None and finding.subject == "false_premise" and "premise" in finding.subject


@pytest.mark.parametrize(
    "extra",
    [
        {"acme/trace.py": "import os\n\nON = os.environ.get('ACME_TRACE') == '1'\n"},  # code reads it
        {".env.example": "ACME_TRACE=0\n"},  # a dotenv file
        {"docs/ops.md": "Set `ACME_TRACE=1` to print queries.\n"},  # documented: occurrence counts
    ],
)
def test_a_name_with_any_occurrence_resolves(tmp_path, extra):
    prompt = "acme already prints every query when ACME_TRACE=1 is set, so switch that on in CI."
    assert not _check(_repo(tmp_path, extra), prompt).missing


def test_a_member_resolves_through_code_but_not_through_prose(tmp_path):
    prompt = "Build it on the existing Store.shift() helper."
    in_prose = _repo(tmp_path / "a", {"README.md": "Items shift between stores.\n"})
    assert [a.name for a in _check(in_prose, prompt).missing] == ["Store.shift()"]
    in_code = _repo(tmp_path / "b", {"acme/extra.py": "def shift():\n    pass\n"})
    assert not _check(in_code, prompt).missing
    in_changelog = _repo(tmp_path / "c", {"CHANGELOG.md": "Removed `Store.shift()` in 0.4.\n"})
    assert not _check(in_changelog, prompt).missing  # an occurrence anywhere: precision first


def test_flags_and_config_keys_resolve_where_they_are_defined(tmp_path):
    flagged = _repo(tmp_path / "a", {"acme/cli.py": "parser.add_argument('--dry-run')\n"})
    assert not _check(flagged, "Pass the --dry-run flag when the job syncs.").missing
    keyed = _repo(tmp_path / "b", {"service.toml": "[http]\nretry_budget = 3\n"})
    assert not _check(keyed, "Use the existing `retry_budget` setting for this.").missing


# -- what is not ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        # creating it
        "Add Store.shift(sku, qty) on top of the existing Store.take() helper.",
        "I need Store.shift(sku, qty) to move stock between stores.",
        "Order gets an optional discountCode, the code the customer typed.",
        "Rename the `legacy_mode` option to `compat_mode` everywhere, and drop `legacy_mode`.",
        "Client's `delay` becomes `delay_s`; drop the old name.",
        "Please add an ACME_TRACE=1 switch that prints every query, and turn it on in CI.",
        "Make acme print every query when ACME_TRACE=1 is set.",
        "Implement Store.audit() following the README.",
        # not asserting anything
        "test_take in tests/test_store.py is failing. Please fix it.",
        "Fix the CSV export's `issued` column so it is ISO.",
        "Delete scratch/old_notes.txt and tmp/debug.log, nothing else.",
        "Statements must keep DD/MM/YYYY and the API sends X-Api-Version: 3.12.",
        "Rebuild with `mybuild develop --release` and confirm it works.",
        # external things
        "Use the existing node:fs helpers and the `X-Request-Id` header from https://example.com/api.",
        "Use version 3.4.1 of the client.",
    ],
)
def test_ordinary_requests_and_new_names_are_silent(tmp_path, prompt):
    assert not _check(_repo(tmp_path), prompt).missing


def test_a_name_created_anywhere_in_the_request_is_no_premise_anywhere(tmp_path):
    prompt = "Add a `quiet_mode` option. Then use the existing `quiet_mode` option in the CLI."
    assert not _check(_repo(tmp_path), prompt).missing


def test_without_an_index_nothing_is_said(tmp_path):
    assert not premise.check("Use the existing ACME_TRACE switch.", _repo(tmp_path), None).missing


def test_several_missing_names_make_one_note(tmp_path):
    found = _check(_repo(tmp_path), "Use the existing ACME_TRACE and ACME_LEVEL switches together.")
    assert found.note.startswith("`ACME_TRACE` and `ACME_LEVEL` appear nowhere")


# -- through the engine and the Codex adapter -------------------------------------------------------


def _prompt(repo: Path, text: str, session: str = "s") -> dict:
    return {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
    }


def test_the_note_reaches_the_agent_once_per_session(tmp_path):
    repo = _repo(tmp_path)
    ask = "acme already prints every query when ACME_TRACE=1 is set, so switch that on in CI."
    guard = Guard(Settings())
    try:
        guard.workspace(repo).index.ready(timeout=30)
        first, _r, decision = translate.dispatch(guard, _prompt(repo, ask))
        again, _r, _d = translate.dispatch(guard, _prompt(repo, ask))
        other_session, _r, _d = translate.dispatch(guard, _prompt(repo, ask, session="s2"))
        routine, _r, _d = translate.dispatch(guard, _prompt(repo, "Fix test_take, it fails.", session="s3"))
    finally:
        guard.close()
    context = first["hookSpecificOutput"]["additionalContext"]
    assert context.startswith("`ACME_TRACE` appears nowhere in this repository")
    assert [f.subject for f in decision.findings] == ["false_premise"]
    assert again == {}  # once per name per session
    assert other_session["hookSpecificOutput"]["additionalContext"] == context
    assert routine == {}
