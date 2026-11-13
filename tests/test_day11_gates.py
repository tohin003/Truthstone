"""Day 11 (fix-r7): request readings that do not depend on how the request refers to its test.

Every golden task has three phrasings of one request; the guard read "make this failing test pass" in the
canonical and conversational phrasings of several tasks and not in the terse one, because a path, a pytest
node id or a long quoted title sat between "make" and "pass" (or between "test" and "failing"). The readers
now see the test reference as one word (``validate/testrefs.py``), wherever it sits:

* test pressure (``spec_integrity.test_pressure_requested``): one test per way of naming the test, and the
  look-alikes that must stay silent ("the tests pass; refactor", "add a test", "why does it fail?", "skip
  it", "delete it", "make sure the suite passes", predicted and excused failures);
* keeps the tests (``keep_reading.tests_kept_requested``): the family of forms, each position;
* the readers that exempt a check: a test title's words are not a skip asked for, "fix it so npm test is
  green" asks nothing of the tests, "fixing" a named test is making it pass, a failing test the request
  describes is not a red phase it asked for, "documented in the README" cites the docs;
* the spec note: the terse shape gets the note at prompt time; a routine prompt reads no file.

Made-up project throughout (``kettlewick``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.stop_session import make_repo
from truthstone.adapters.codex import translate
from truthstone.core.config import NotesSettings, Settings
from truthstone.core.engine import Guard
from truthstone.planning import spec_note
from truthstone.repo.index import RepoIndex
from truthstone.validate import keep_reading, spec_integrity, testrefs, weakened_tests
from truthstone.verify import claims

KEEP = "don't edit the tests"
README = """# kettlewick

Kettlewick schedules brews for the tea shop.

## Brewing

A brew never runs past its steep limit: the limit is part of the brewing contract.
"""
BREW = '''"""Brews."""


def steep(brew, minutes):
    """Steep ``brew`` for ``minutes``.

    A brew never runs past its steep limit: longer steeps are refused.
    """
    if minutes > brew.limit:
        raise ValueError("past the steep limit")
    return minutes
'''
TESTS = """from types import SimpleNamespace

from kettlewick.brew import steep


def test_steep_within_limit():
    assert steep(SimpleNamespace(limit=5), 4) == 4


def test_a_long_steep_runs_past_the_limit_for_iced_tea():
    assert steep(SimpleNamespace(limit=5), 9) == 9
"""
JS_TESTS = """import { test } from "node:test";
import assert from "node:assert";
import { steep } from "../src/brew.ts";

test("iced tea may steep past the limit", () => {
  assert.equal(steep({ limit: 5 }, 9), 9);
});
"""
REPO = {
    "README.md": README,
    "pyproject.toml": '[project]\nname = "kettlewick"\nversion = "0.1.0"\n',
    "src/kettlewick/__init__.py": "",
    "src/kettlewick/brew.py": BREW,
    "tests/test_brew.py": TESTS,
    "test/brew.test.ts": JS_TESTS,
}
NAME = "test_a_long_steep_runs_past_the_limit_for_iced_tea"
NODE = f"tests/test_brew.py::{NAME}"
TITLE = "iced tea may steep past the limit"


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


@pytest.fixture
def index(tmp_path: Path) -> RepoIndex:
    return RepoIndex(make_repo(tmp_path / "repo", REPO)).build()


def pressure(prompt: str, idx=None) -> bool:
    return spec_integrity.test_pressure_requested(prompt, idx)


# -- test pressure: the test named any way -----------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        f"Make {NAME} pass; {KEEP}.",  # bare pytest name
        f"Make tests/test_brew.py pass; {KEEP}.",  # file path
        f"Make {NODE} pass along with the rest of the suite; {KEEP}.",  # node id between make and pass
        f"Get `pytest tests/test_brew.py -k {NAME}` passing; {KEEP}.",  # path -k name
        f"CI is red on {NAME}. Fix it; {KEEP}.",  # CI is red
        f"The suite is red (tests/test_brew.py). Get it green; {KEEP}.",  # the suite is red
        f'"{TITLE}" (test/brew.test.ts) fails. Fix the code; {KEEP}.',  # quoted title, file after it
        f'test/brew.test.ts "{TITLE}" fails: the brew is refused. Fix it.',  # file, then title
        f"Fix {NODE}; {KEEP}.",  # "fix X" with no "pass"
        f"{NODE} is failing: steep() refuses it. Please fix it.",  # long node id, then failing
        f'Failing tests: "{TITLE}" and "a second brew may steep past it too". Fix steep().',  # chained titles
        "main is red since #12 (tests/test_brew.py). Get main green.",  # red, then the file
        f'The brew test in test/brew.test.ts ("{TITLE}") is red. Could you fix it?',  # title in brackets
        f"{NAME} must pass; {KEEP}.",  # "should / must pass"
        "Make test/brew.test.ts pass without changing the tests.",  # JS file path
    ],
)
def test_a_named_failing_test_is_test_pressure_however_it_is_named(prompt):
    assert pressure(prompt) is True


def test_a_title_named_with_no_test_word_is_resolved_against_the_repository(index):
    prompt = f'Make "{TITLE}" pass; {KEEP}.'
    assert pressure(prompt) is False  # the sentence alone does not say it is a test
    assert pressure(prompt, index) is True  # the repository's test file holds that title


def test_a_file_the_repository_does_not_have_is_no_reference(index):
    assert pressure("Make tests/test_kettle_timer.py pass.", index) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "The tests pass; refactor steep() into two functions.",
        "Add a test for steep() with a zero-minute brew.",
        f"Why does {NAME} fail?",
        "Why does the brew test fail on my machine?",
        f"Skip {NAME} for now.",
        f"Skip the failing {NAME} until the supplier answers.",
        "Delete tests/test_old_brew.py, nothing imports it any more.",
        "Rename steep to steep_for and make sure the suite passes.",
        f"{NAME} will fail after the limit change; update it.",
        "tests/test_brew.py fails here because it needs the network; leave it alone.",
        '"total due amount" fails validation on the invoice export.',
        "Keep the tests passing while you split brew.py.",
    ],
)
def test_look_alikes_are_not_a_request_for_a_failing_test_to_pass(prompt):
    assert pressure(prompt) is False


def test_a_why_question_with_a_fix_asked_is_pressure():
    assert pressure(f"Why does {NAME} fail? Fix it, please.") is True


def test_the_three_phrasings_of_one_request_agree():
    canonical = (
        f"CI is red on {NAME} in tests/test_brew.py. Please make the whole suite pass. {KEEP.capitalize()}."
    )
    conversational = f"ci's red on {NAME} in tests/test_brew.py. can you make the suite pass? {KEEP} though"
    terse = f"Make {NODE} pass along with the rest of the suite; {KEEP}."
    readings = {
        (weakened_tests.tests_kept_requested(p), pressure(p)) for p in (canonical, conversational, terse)
    }
    assert readings == {(True, True)}


# -- keeps the tests: the family of forms, any position ----------------------------------------------------


@pytest.mark.parametrize(
    "clause",
    [
        "don't edit the tests",
        "don't touch the tests",
        "don't change the tests",
        "don't modify the tests",
        "the tests stay as they are",
        "tests remain unchanged",
        "the tests are the spec",
        "no test changes",
        "no changes to the tests",
        "do it without touching tests",
        "with the tests unchanged",
        "keep the tests as-is",
        f"don't edit {NODE}",
    ],
)
@pytest.mark.parametrize("first", [False, True])
def test_the_keep_family_reads_wherever_it_sits(clause, first):
    ask = f"make {NAME} pass"
    prompt = (
        f"{clause[0].upper() + clause[1:]}: {ask}." if first else f"{ask[0].upper() + ask[1:]}; {clause}."
    )
    assert keep_reading.tests_kept_requested(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        "Update the tests to the new steep limit.",
        "The tests are wrong about the limit; fix them.",
        "No need to run the tests for this docs change.",
        "Make sure the tests stay green after the refactor.",
        "You may change the tests if the limit moves.",
        "Add tests for the iced tea case.",
    ],
)
def test_keep_look_alikes_are_not_keep(prompt):
    assert keep_reading.tests_kept_requested(prompt) is False


# -- the readers that exempt a check -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        # a title's own words are not the request's ("disabled" in a title is not a skip asked for)
        'The test "baristas can preview a disabled blend" in test/brew.test.ts is failing. Get it green.',
        # un-skipping is not a skip
        "Record a fresh supplier snapshot so the contract test stops skipping.",
        # a purpose clause asks nothing of the tests
        "Two tests (test/brew.test.ts, test/menu.test.ts) failed since the cleanup; "
        "fix it so npm test is green.",
        # fixing a named failing test is making it pass
        f'Please fix the test "{TITLE}" in test/brew.test.ts.',
        f"Fix {NODE}: steep() refuses nine minutes.",
        f'Fix the failing test "{TITLE}" in test/brew.test.ts.',
        # a noun is not the verb ("the alignment test")
        'the menu alignment test in test/menu.test.ts ("menu lines up the prices") is red. could you fix it?',
    ],
)
def test_wording_that_asks_nothing_of_the_tests_is_no_test_change_request(prompt):
    assert weakened_tests.tests_change_requested(prompt) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "Update the tests to the new steep limit.",
        "Fix the tests so they expect the new limit.",
        f"Skip {NAME} for now.",
        "The spec is clear that empty brews are invalid; test_accepts_empty_brew contradicts it. "
        "Remove or invert that test.",
        "We don't support the iced endpoint any more: delete it and its tests.",
        "The steep limit tests are outdated.",
    ],
)
def test_real_test_change_requests_still_read(prompt):
    assert weakened_tests.tests_change_requested(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        f'test/brew.test.ts has a new failing test, "{TITLE}". Please make the suite pass; {KEEP}.',
        "Failing tests: two in tests/test_brew.py. Fix steep().",
        f"{NODE} reproduces it. Please fix it.",
    ],
)
def test_a_failing_test_the_request_describes_is_not_a_red_phase(prompt):
    assert claims.red_phase_requested(prompt) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "Add a failing test that reproduces the over-steep bug first, then fix it.",
        "Use TDD for the iced tea limit.",
        "Write a regression test before you change steep().",
    ],
)
def test_a_red_phase_asked_for_still_reads(prompt):
    assert claims.red_phase_requested(prompt) is True


def test_a_rule_documented_in_the_readme_is_cited_not_a_doc_change():
    assert (
        spec_integrity.doc_change_requested("The rule is documented in the README. Please get CI green.")
        is False
    )
    assert (
        spec_integrity.doc_change_requested("CI is red (rule documented in the README); get CI green.")
        is False
    )
    assert spec_integrity.doc_change_requested("Make sure the new limit is documented in the README.") is True
    assert spec_integrity.doc_change_requested("Document the iced tea limit in the README.") is True


# -- test references ---------------------------------------------------------------------------------------


def test_references_are_masked_as_one_word():
    masked = testrefs.mask(f'Make {NODE} and "{TITLE}" in test/brew.test.ts pass.')
    assert masked == "Make testref and testref in testref pass."


def test_code_and_short_quotes_are_not_titles():
    assert testrefs.refs('The test prints "x = steep(b, 9)" and "ok"') == []


# -- the spec note -----------------------------------------------------------------------------------------


def _prompt(guard: Guard, repo: Path, text: str, session: str = "s1") -> str:
    payload = {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
    }
    out, _rendering, _decision = translate.dispatch(guard, payload)
    return str((out or {}).get("hookSpecificOutput", {}).get("additionalContext", "") or "")


@pytest.mark.parametrize(
    "prompt",
    [
        f"Make {NODE} pass along with the rest of the suite; {KEEP}.",
        "Make test/brew.test.ts pass without changing the tests.",
        f'Tests are the spec: "{TITLE}" has to pass.',
    ],
)
def test_the_terse_shapes_get_the_spec_note(tmp_path, prompt):
    repo = make_repo(tmp_path / "repo", REPO)
    guard = Guard(Settings(notes=NotesSettings(feasibility=False)))
    try:
        guard.workspace(repo).index.ready(timeout=30)
        said = _prompt(guard, repo, prompt)
    finally:
        guard.close()
    assert said.startswith(spec_note.LEAD_ONE[:40]) and "steep limit" in said
    assert "premise" not in said.lower()


def test_a_routine_prompt_touches_no_index():
    touched: list[str] = []

    class Index:
        @property
        def is_built(self):
            touched.append("is_built")
            return True

        @property
        def files(self):
            touched.append("files")
            return {}

    assert spec_note.render(f"Rename steep() and keep {NAME} green.", Index()) is None
    assert touched == []


# -- the excuse that makes spec erosion recorded-only ------------------------------------------------------


def _erosion(text: str):
    from types import SimpleNamespace

    return SimpleNamespace(sentence=SimpleNamespace(text=text), counterpart="", path="README.md")


RULE = "A brew is refused when it would steep past its limit."


@pytest.mark.parametrize(
    "prompt",
    [
        # the words of a quoted test title are the test's, not a request to change the rule
        'Support added a test in test/brew.test.ts ("a brew past its limit is refused unless iced"). '
        "Get npm test green; don't change the tests.",
        # "support" the noun
        "Support ticket KW-12: a brew past its limit was refused at the counter. Make test/brew.test.ts "
        "pass.",
        # "lower" the adjective
        "Brews named in lower case steep past their limit and are refused; fix steep().",
    ],
)
def test_wording_that_names_no_rule_change_does_not_excuse_an_erosion(prompt):
    assert spec_integrity.rule_change_requested(prompt, _erosion(RULE)) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "Support brews past their limit when they are iced: allow a long steep for iced tea.",
        "Stop refusing a brew past its limit; iced tea may steep longer.",
        "Lower the steep limit check: a brew may run past its limit.",
    ],
)
def test_a_request_to_change_the_rule_still_excuses_it(prompt):
    assert spec_integrity.rule_change_requested(prompt, _erosion(RULE)) is True


def test_a_quoted_span_is_looked_up_only_in_a_sentence_about_a_test_outcome(index, monkeypatch):
    reads: list[str] = []
    real = testrefs._read
    monkeypatch.setattr(testrefs, "_read", lambda root, path: reads.append(path) or real(root, path))
    testrefs.mask('The menu shows "iced tea may steep longer" on the board.', index)
    assert reads == []  # no outcome word: nothing read
    assert testrefs.mask(f'Make "{TITLE}" pass.', index) == "Make testref pass."
    assert reads  # resolved against the repository's test files


@pytest.mark.parametrize(
    "prompt",
    [
        f"Keep working on steep() until {NAME} passes.",
        f"QA added {NAME} for KW-1; make it work without touching the tests.",
        "Make the kill-switch test from the review pass; tests stay as they are.",
        f"Please sort out {NAME}.",
    ],
)
def test_more_ways_to_ask_for_a_named_test_to_pass(prompt):
    assert pressure(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        "Make the existing tests still pass.",
        "Implement the cache and iterate until the tests pass.",
        "Make the tests and the linter pass after the rename.",
        "Add the iced option and make it work offline.",
    ],
)
def test_their_routine_look_alikes_stay_silent(prompt):
    assert pressure(prompt) is False
