"""G19: the Claude study's work account takes every pair it can; personal only as a fallback."""

from __future__ import annotations

import time

from truthstone.bench.codex import claude


def _reading(session: float, week: float) -> dict:
    now = time.time()
    return {
        "session": {"used_percent": session, "resets_at": now + 3600},
        "week": {"used_percent": week, "resets_at": now + 86400},
    }


def test_work_is_chosen_even_with_less_headroom():
    policy = claude.AccountPolicy()
    choice = claude.choose_account({"work": _reading(60.0, 50.0), "personal": _reading(5.0, 10.0)}, policy)
    assert choice.account == "work"


def test_personal_only_when_work_cannot_take_a_pair():
    policy = claude.AccountPolicy()
    choice = claude.choose_account({"work": _reading(99.0, 50.0), "personal": _reading(5.0, 10.0)}, policy)
    assert choice.account == "personal"
