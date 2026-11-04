"""The no-leakage lint's hashed list is current, and holds every golden task id."""

from __future__ import annotations

import json

from truthstone.bench.codex import leakage, suite


def test_the_stored_list_matches_the_tasks():
    """Rebuild with `python -m truthstone.bench.codex leakage --write` after any task change."""
    stored = json.loads(leakage.LIST_PATH.read_text(encoding="utf-8"))
    built = {k: v for k, v in leakage.build().items() if not k.startswith("_")}
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
