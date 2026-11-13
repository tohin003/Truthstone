"""The no-leakage lint's hashed list is current, and holds every golden task id."""

from __future__ import annotations

import json
import sys

import pytest

from truthstone.bench.codex import leakage, suite

# The strings leave out Python's own vocabulary, read from the running interpreter's standard
# library (`leakage._generic`), so only the minor version that built the stored list rebuilds them
# exactly: under 3.12, 2 of its 2,446 strings drop out and 1 comes in. The ids do not depend on it.
BUILT_WITH = (3, 13)


@pytest.fixture(scope="module")
def built() -> dict:
    return {k: v for k, v in leakage.build().items() if not k.startswith("_")}


def test_the_stored_ids_match_the_tasks(built):
    stored = json.loads(leakage.LIST_PATH.read_text(encoding="utf-8"))
    assert stored["ids"] == built["ids"]


@pytest.mark.skipif(
    sys.version_info[:2] != BUILT_WITH,
    reason="the stored strings are built with Python 3.13's stdlib vocabulary",
)
def test_the_stored_list_matches_the_tasks(built):
    """Rebuild with `python -m truthstone.bench.codex leakage --write` under Python 3.13 after any
    task change."""
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
