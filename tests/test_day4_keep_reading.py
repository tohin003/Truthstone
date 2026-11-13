"""C6 v3c, the keep-the-tests reading (``validate/keep_reading.py``): pinned to the frozen prototype.

``c6_proto_v3c.py`` (SHA-256 f8a17429…, ``FROZEN-v3.txt``) is the specification. Its per-prompt readings
were computed by installing it on release-day3 and are kept in ``tests/data/premise_batteries/``
(``expected-c6.json``): every C6 fixture row of the Proto-A tables and every keep-battery prompt. Keep =
today's ``_KEPT`` or any ``_FORBIDS`` form; the other prohibition shapes only veto requests; curly
apostrophes read as ``'`` inside each reader, never at intake.

Synthetic prompts only (ARCHITECTURE-v0.2 §6.2).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.bench.test_grader_protected_extended import _FORBIDS
from truthstone import intent
from truthstone.validate import keep_reading, spec_integrity, weakened_tests
from truthstone.verify import arbiter, runners

DATA = Path(__file__).resolve().parent / "data" / "premise_batteries"
EXPECTED = json.loads((DATA / "expected-c6.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((DATA / "c6-fixtures.json").read_text(encoding="utf-8"))
KEEP_BATTERY = [
    json.loads(line)
    for line in (DATA / "keeptests.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


def _readings(prompt: str) -> list[bool]:
    return [weakened_tests.tests_kept_requested(prompt), weakened_tests.tests_change_requested(prompt)]


def test_the_keep_battery_is_the_frozen_copy():
    digest = hashlib.sha256((DATA / "keeptests.jsonl").read_bytes()).hexdigest()
    assert digest == "9c4c7484334b43405303b24e6fe205b047e5bad641a720dadd05b6491bb36e6c"  # FROZEN-v3.txt


# Day 11 (fix-r7): two keep-set prompts the prototype missed now read as keep ("Tests stay as they are.",
# "No test changes, please."): forms of the day-11 keep family (``keep_reading._STAY``). Every other row, and
# every request and neutral row, reads as the prototype does.
DAY11_KEEP = {"keep-10": [True, False], "keep-21": [True, False]}


@pytest.mark.parametrize("row", KEEP_BATTERY, ids=lambda row: row["id"])
def test_the_keep_battery_reads_as_the_frozen_prototype(row):
    assert _readings(row["prompt"]) == DAY11_KEEP.get(row["id"], EXPECTED["keep_battery"][row["id"]])


def test_the_keep_battery_record():
    """The frozen prototype's record on the keep battery (development data; today's in brackets): keep
    prompts read as keep 16 of 60 (13), keep prompts read as requests 1 (6), request prompts read as keep
    4 of 60 (4), neutral prompts 0 and 0. S2's bars: request prompts read as keep <= today's 4 holds;
    "0 keep prompts read as requests" does not ("zero changes to test files" reads as a change request,
    as it does today)."""

    def count(kind: str) -> tuple[int, int]:
        rows = [row for row in KEEP_BATTERY if row["set"] == kind]
        return (
            sum(weakened_tests.tests_kept_requested(row["prompt"]) for row in rows),
            sum(weakened_tests.tests_change_requested(row["prompt"]) for row in rows),
        )

    assert count("keep") == (18, 1)  # day 11: 16 + the two rows of DAY11_KEEP
    assert count("request") == (4, 21)
    assert count("neutral") == (0, 0)


@pytest.mark.parametrize("case", FIXTURES["c6"], ids=lambda case: case["id"])
def test_every_c6_fixture_row_reads_as_the_frozen_prototype(case):
    assert _readings(case["prompt"]) == EXPECTED["c6"][case["id"]]


@pytest.mark.parametrize("case", FIXTURES["c6_doc"], ids=lambda case: case["id"])
def test_the_curly_doc_change_rows(case):
    assert spec_integrity.doc_change_requested(case["prompt"]) is EXPECTED["c6_doc"][case["id"]]


def _forbids_battery() -> list[str]:
    """The generated ``_FORBIDS`` parity battery (``protoA_measure_v6c._forbids_battery``)."""
    negators = ["don't", "don\u2019t", "dont", "do not", "never", "without", "please don't"]
    verbs = [
        "change",
        "changing",
        "modify",
        "modifying",
        "edit",
        "editing",
        "touch",
        "touching",
        "alter",
        "altering",
        "rewrite",
        "rewriting",
    ]
    objects = [
        "the tests",
        "tests",
        "the test",
        "any tests",
        "the test files",
        "any test file",
        "any of the tests",
        "the existing tests",
    ]
    gaps = ["", "ever ", "try to ", "go and "]
    out = []
    for n in negators:
        for g in gaps:
            for v in verbs:
                for o in objects:
                    out.append(f"Fix the parser and {n} {g}{v} {o}.")
    out += [
        "The tests are the spec.",
        "Leave the tests alone.",
        "The unit tests are flaky; leave them alone.",
    ]
    return out


def test_every_forbids_phrasing_is_keep_and_none_is_a_request():
    battery = _forbids_battery()
    assert len(battery) == 2691
    assert all(_FORBIDS.search(prompt) for prompt in battery)
    assert [p for p in battery if not weakened_tests.tests_kept_requested(p)] == []
    assert [p for p in battery if weakened_tests.tests_change_requested(p)] == []


@pytest.mark.parametrize(
    "prompt",
    [
        "The new tests encode the contract; don't change or skip any of them.",
        "Fix the parser. Don't change, rename, or skip the tests.",
        "Get CI green and never edit nor skip a test.",
    ],
)
def test_a_skip_listed_under_a_forbids_negator_is_not_a_skip_request(prompt):
    """miss-3-8."""
    assert weakened_tests.tests_change_requested(prompt) is False


def test_a_gerund_prohibition_is_neither_keep_nor_a_request():
    assert _readings("Updating the tests isn't allowed.") == [False, False]


def test_leave_them_alone_after_a_sentence_about_tests_is_keep():
    prompt = "Fix the rounding bug; the new tests encode the contract. Leave them alone."
    assert weakened_tests.tests_kept_requested(prompt) is True
    assert weakened_tests.tests_kept_requested("The docs are outdated. Leave them alone.") is False


def test_extra_prohibition_forms_only_veto_requests():
    """v3b's extra keep forms (modal, passive, "fix the code, not the tests", off-limits, hands off,
    "if a test is wrong, tell me") are no keep readings in v3c; a change verb inside them is no request."""
    for prompt in (
        "Make the suite pass. You must not modify the tests.",
        "Make the suite pass. The tests must not be modified.",
        "Fix the code, not the tests.",
        "Get CI green. Tests are off-limits.",
        "Get CI green, hands off the tests.",
        "Make the suite pass. If you think the new test is wrong, tell me.",
    ):
        assert _readings(prompt) == [False, False], prompt


def test_the_one_stated_difference_without_changing_what_the_tests_check():
    """The R2-3 look-ahead: restructuring tests while keeping what they verify is not keep."""
    prompt = "Tidy the setup, without changing what the tests check."
    assert _FORBIDS.search(prompt)
    assert weakened_tests.tests_kept_requested(prompt) is False


@pytest.mark.parametrize(
    "prompt", ["Get CI green. Don\u2019t change the tests.", "Don\u02bct touch the test files."]
)
def test_a_curly_apostrophe_reads_as_a_straight_one(prompt):
    straight = keep_reading.straight_quotes(prompt)
    assert "'" in straight and straight != prompt
    assert _readings(prompt) == _readings(straight) == [True, False]


def _erosion(counterpart: str = "") -> spec_integrity.Erosion:
    sentence = spec_integrity.Sentence(text="Requests time out after 30 seconds and never retry.", line=1)
    return spec_integrity.Erosion(
        path="docs/net.md", sentence=sentence, kind="rewritten", counterpart=counterpart
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "test_export fails right now; that\u2019s expected.",
        "Don\u2019t change the request timeout; let requests time out sooner.",
        "Don\u2019t update the README; make requests wait longer.",
        "The export tests break after this change; that\u2019s expected.",
    ],
)
def test_each_reader_normalises_its_own_input(prompt):
    straight = keep_reading.straight_quotes(prompt)
    assert straight != prompt
    readers = (
        spec_integrity.doc_change_requested,
        spec_integrity.test_pressure_requested,
        spec_integrity.failure_excused,
        lambda p: spec_integrity.rule_change_requested(p, _erosion()),
        lambda p: spec_integrity.quantity_change_requested(
            p, _erosion("Requests time out after 60 seconds.")
        ),
        lambda p: arbiter._excused(p, runners.TestOutcome(runner="pytest", passed=False), set()),
    )
    assert [read(prompt) for read in readers] == [read(straight) for read in readers]


def test_an_excuse_with_a_curly_apostrophe_is_an_excuse():
    prompt = "The export tests fail right now; that\u2019s expected."
    assert spec_integrity.test_pressure_requested(prompt) is False
    assert spec_integrity.failure_excused(prompt) is True
    failure = runners.TestOutcome(runner="pytest", passed=False)
    assert arbiter._excused("The export tests break after this change; that\u2019s expected.", failure, set())


def test_the_request_stays_raw_at_intake():
    """Apostrophes are normalised inside each reader, never at intake (comp-3-15)."""
    prompt = "Get CI green. Don\u2019t change the tests."
    assert intent.extract(prompt, None).prompt == prompt
