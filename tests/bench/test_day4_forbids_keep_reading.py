"""C6 v3c (day 4): every registered golden prompt that matches the bench's ``_FORBIDS`` reads as keep.

The keep reading is ``_FORBIDS`` parity (``validate/keep_reading.py``). The one stated difference is
the R2-3 look-ahead: "without changing what the tests check" restructures tests and keeps what they
verify, so a prompt whose every ``_FORBIDS`` match is that form is left out. A miss names the suite and
the task id only (rd1-3-19).
"""

from __future__ import annotations

import re

import pytest

from tests.bench.test_grader_protected_extended import _FORBIDS
from truthstone.bench.codex import suite
from truthstone.validate import weakened_tests

# The R2-3 look-ahead's words, right after a _FORBIDS match.
_R23_CONTINUATION = re.compile(
    r"\s+(?:check|test|assert|cover|verif|logic|behaviou?r|coverage|semantics|intent)\w*", re.IGNORECASE
)
GOLDEN = sorted(name for name in suite.SUITES if name.startswith("golden-"))


def test_the_golden_suites_are_read():
    spent = {"golden-dev", "golden-heldout", "golden-heldout2", "golden-heldout3", "golden-candidates"}
    assert spent <= set(GOLDEN)


@pytest.mark.parametrize("name", GOLDEN)
def test_every_forbids_prompt_reads_keep(name):
    misses = set()
    for task in suite.load_suite(suite=name):
        for phrasing in suite.PHRASINGS:
            prompt = task.prompt(phrasing)
            matches = list(_FORBIDS.finditer(prompt))
            if not matches or all(_R23_CONTINUATION.match(prompt, m.end()) for m in matches):
                continue
            if not weakened_tests.tests_kept_requested(prompt):
                misses.add(f"{name} {task.id}")
    assert not misses, "_FORBIDS prompts not read as keep: " + ", ".join(sorted(misses))
