"""The no-leakage lint's hashed list is current, and holds every golden task id."""

from __future__ import annotations

import hashlib
import json
import sys

import pytest

from truthstone.bench.codex import leakage, suite

# The strings depend on two inputs of the machine that builds them, besides the tasks:
# * Python's own vocabulary, read from the running interpreter's standard library
#   (`leakage._generic`): under 3.12, 2 of the 2,446 stored strings drop out and 1 comes in
#   (3.13.15 and 3.13.16 build the same list; so does python.org's 3.13.17 on GitHub's macOS
#   runner, since the stdlib's own test suites are left out: it ships `idlelib/idle_test`,
#   whose identifiers took 3 stored strings out of the list while they were read);
# * the English words that are not "invented words", read from /usr/share/dict/words
#   (`leakage.WORDS`, macOS's web2): without it, as on Ubuntu's runner image, 252 more come in.
# The ids depend on neither.
BUILT_WITH_PYTHON = (3, 13)
BUILT_WITH_WORDS_SHA256 = "be41ad97963bf8dabedd5871d5d691596175269d540956b0f9965a885c2bbab9"


def _other_build_machine() -> str:
    """Why this machine cannot rebuild the stored strings exactly, or "" when it can."""
    if sys.version_info[:2] != BUILT_WITH_PYTHON:
        return "the stored strings are built with Python 3.13's stdlib vocabulary"
    try:
        words = hashlib.sha256(leakage.WORDS.read_bytes()).hexdigest()
    except OSError:
        return f"the stored strings are built with macOS's {leakage.WORDS}; this machine has none"
    if words != BUILT_WITH_WORDS_SHA256:
        return f"the stored strings are built with macOS's {leakage.WORDS}; this machine's differs"
    return ""


@pytest.fixture(scope="module")
def built() -> dict:
    return {k: v for k, v in leakage.build().items() if not k.startswith("_")}


def test_the_stored_ids_match_the_tasks(built):
    stored = json.loads(leakage.LIST_PATH.read_text(encoding="utf-8"))
    assert stored["ids"] == built["ids"]


@pytest.mark.skipif(bool(_other_build_machine()), reason=_other_build_machine() or "-")
def test_the_stored_list_matches_the_tasks(built):
    """Rebuild with `python -m truthstone.bench.codex leakage --write` on macOS under Python 3.13
    after any task change."""
    stored = json.loads(leakage.LIST_PATH.read_text(encoding="utf-8"))
    assert stored == built


def test_every_golden_task_id_is_listed_and_no_string_is_plain():
    stored = json.loads(leakage.LIST_PATH.read_text(encoding="utf-8"))
    ids = set(stored["ids"])
    for name in leakage.GOLDEN_SUITES:
        for task in suite.load_suite(suite=name):
            assert leakage.digest(task.id) in ids
    assert all(len(h) == 64 and int(h, 16) >= 0 for h in stored["strings"])  # hashes only


def test_code_like_names_and_invented_words_are_kept_and_english_is_not():
    words = {"transfer", "inventory", "trim", "plan"}
    assert leakage._code_like("split_on_comma") and leakage._code_like("parseWindow")
    assert not leakage._code_like("inventory")
    assert leakage._englishish("transfers", words) and leakage._englishish("trimmed", words)
    assert leakage._englishish("planned", words) and not leakage._englishish("zorbletrix", words)
