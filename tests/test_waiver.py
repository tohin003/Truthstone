"""G6: the test waiver is an instruction, not a substring.

The old waiver was a substring list, so "…has no tests; fix it and add tests" waived
verification (probe G), and D2 found 11 of 12 paraphrases of a real instruction missed
and 4 of 5 ordinary prompts falsely waived. The two Pebble tests are ported from
`pebble/backend/tests/test_guard_gate_gaps_24.py` (V1-093).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction, EventType, GateResult
from truthstone.core.events import AgentEvent
from truthstone.core.taskstate import TaskState
from truthstone.intent import waiver
from truthstone.intent.models import TaskSpec
from truthstone.repo import RepoIndex
from truthstone.verify import completion_gate

FIXTURES = Path(__file__).parent / "fixtures"
COVERED = "src/shop/utils/pagination.py"  # tests/test_pagination.py covers it
UNTESTED = "src/shop/api/orders.py"  # nothing covers it

# The substring list this replaces, kept to measure against.
OLD_PHRASES = (
    "do not run test", "don't run test", "dont run test", "without running test",
    "no need to run test", "skip the test", "skip tests", "don't test",
    "do not run the test", "no tests", "without tests", "don't run the test",
)


def old_waived(prompt: str) -> bool:
    return any(phrase in prompt.lower() for phrase in OLD_PHRASES)


# 12 paraphrases of "do not run the tests" and 5 ordinary prompts that mention tests.
PARAPHRASES = [
    "Rename the helper. Don\N{RIGHT SINGLE QUOTATION MARK}t run the tests.",
    "Bump the version; no need to run the test suite.",
    "Update the docstring - no tests needed.",
    "Just fix the typo, you don't need to run the tests.",
    "Fix the import. There's no need to run the tests this time.",
    "Please don't bother running the tests, CI will do it.",
    "Change the log message. Skip running the test suite.",
    "Tweak the README wording; tests aren't needed.",
    "Update the copyright year. No tests.",
    "Refactor this quickly and don't worry about the tests.",
    "Fix the comment, never run the full test suite here.",
    "Document add in calc.py without running the tests.",
]
ORDINARY = [
    "The payments module has no tests; fix the rounding bug and add tests.",
    "Make sure there are no tests failing before you finish.",
    "This shipped without tests; add some.",
    "Update calc.py so add documents its behaviour; the docs folder has no tests in it.",
    "No tests yet, so just implement the parser.",
]


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


def _gate(prompt: str, index: RepoIndex, touched: str = COVERED):
    from truthstone.complexity import assess
    from truthstone.intent import extract

    spec = extract(prompt, index)
    spec.complexity = assess(spec, index)
    state = TaskState(task_id="t1", spec=spec)
    state.touch(touched)
    return state, completion_gate.evaluate(state, index)


# -- the instruction ------------------------------------------------------------------------


class TestTheInstruction:
    @pytest.mark.parametrize("prompt", PARAPHRASES)
    def test_a_paraphrase_waives(self, prompt):
        assert TaskSpec(prompt=prompt).tests_waived

    @pytest.mark.parametrize("prompt", ORDINARY)
    def test_an_ordinary_prompt_does_not(self, prompt):
        assert not TaskSpec(prompt=prompt).tests_waived

    def test_the_seventeen_prompt_table(self):
        """Old: 2 of 12 paraphrases waived, 5 of 5 ordinary prompts falsely waived.
        New: 12 of 12, and 0 of 5."""
        assert sum(old_waived(p) for p in PARAPHRASES) == 2
        assert sum(old_waived(p) for p in ORDINARY) == 5
        assert sum(waiver.waives(p) for p in PARAPHRASES) == 12
        assert sum(waiver.waives(p) for p in ORDINARY) == 0

    @pytest.mark.parametrize(
        "prompt",
        [
            "Fix the paginate helper. Do not run tests.",
            "Fix the paginate helper. Don't run the tests.",
            "Fix paginate without running tests.",
            "Fix paginate \N{EM DASH} skip tests.",
            "Fix paginate \N{EN DASH} skip tests.",
            "Fix paginate - skip tests.",
        ],
    )
    def test_the_long_standing_phrasings_still_waive(self, prompt):
        assert waiver.waives(prompt)

    @pytest.mark.parametrize(
        "prompt",
        [
            "Make sure no tests fail after the refactor.",
            "Leave the tests alone and fix the implementation.",
            "Run the tests and fix whatever fails.",
            "Don't test files outside src/ in the linter config.",
        ],
    )
    def test_more_descriptions_are_not_instructions(self, prompt):
        assert not waiver.waives(prompt)

    def test_a_host_supplied_waiver_overrides_the_lexicon(self):
        assert not TaskSpec(prompt="Fix it. Do not run tests.", tests_waiver=False).tests_waived
        assert TaskSpec(prompt="Fix it.", tests_waiver=True).tests_waived

    @pytest.mark.parametrize(
        ("prompt", "requested"),
        [
            ("Add tests for the helpers.", True),
            ("Fix the bug and add a regression test.", True),
            ("Write unit tests for paginate.", True),
            ("Implement the parser with tests.", True),
            ("Cover it with tests.", True),
            ("Write a failing test that reproduces the bug, then fix it.", True),
            ("Run the tests.", False),
            ("Fix the failing tests.", False),
            ("Make sure the tests pass.", False),
            ("Add test ids to the buttons for the e2e suite.", False),
            ("Add test data for the staging seed.", False),
        ],
    )
    def test_tests_requested(self, prompt, requested):
        assert TaskSpec(prompt=prompt).tests_requested is requested


# -- ported from Pebble (test_guard_gate_gaps_24.py) ------------------------------------------


@pytest.mark.parametrize(
    "goal",
    [
        "Update pagination.py so paginate documents its behaviour; the docs folder has no tests in it.",
        "Add tests for the helpers without tests, starting with pagination.py.",
        "Document paginate in pagination.py. There are no tests for the README.",
    ],
)
def test_an_incidental_no_tests_phrase_does_not_waive_the_test_run(repo, goal):
    index = RepoIndex(repo).build()
    state, verdict = _gate(goal, index)
    assert not state.spec.tests_waived
    assert verdict.result is GateResult.INCOMPLETE
    assert "waived" not in verdict.reason


@pytest.mark.parametrize(
    "goal",
    [
        "Document paginate in pagination.py. Do not run the tests.",
        "Document paginate in pagination.py, but don't run tests.",
        "Document paginate in pagination.py without running the tests.",
        "Skip the tests and document paginate in pagination.py.",
    ],
)
def test_an_imperative_still_waives_it(repo, goal):
    assert waiver.waives(goal)
    index = RepoIndex(repo).build()
    _, verdict = _gate(goal, index)
    assert verdict.result is GateResult.PASS
    assert "waived" in verdict.reason


# -- through the Guard ------------------------------------------------------------------------


class Session:
    def __init__(self, repo: Path, session_id: str = "s1") -> None:
        self.repo, self.session_id = repo, session_id
        self.guard = Guard(Settings())
        self.guard.workspace(repo).index.ready(timeout=30)

    def _event(self, kind: EventType, **fields) -> AgentEvent:
        return AgentEvent(
            event=kind, agent="claude-code", workspace=str(self.repo), session_id=self.session_id, **fields
        )

    def prompt(self, text: str):
        return self.guard.handle(self._event(EventType.USER_PROMPT, prompt_text=text))

    def edit(self, path: str, append: str = "\n# changed\n"):
        full = self.repo / path
        full.write_text((full.read_text() if full.exists() else "") + append)
        edit = self._event(EventType.POST_TOOL_USE, tool="Edit", arguments={"file_path": path})
        return self.guard.handle(edit)

    def run(self, command: str, output: str):
        return self.guard.handle(
            self._event(EventType.POST_TOOL_USE, tool="Bash", arguments={"command": command}, result=output)
        )

    def stop(self):
        return self.guard.handle(self._event(EventType.STOP, last_assistant_message="Done."))

    def close(self):
        self.guard.close()


@pytest.fixture
def session(repo):
    s = Session(repo)
    yield s
    s.close()


def test_waiver_persists_within_session(session):
    session.prompt("Fix the paginate helper. Don't run the tests.")
    session.edit(COVERED)
    assert session.stop().action is DecisionAction.ALLOW

    session.prompt("Now also make page 0 behave like page 1.")
    session.edit(COVERED)
    decision = session.stop()
    assert decision.action is DecisionAction.ALLOW, "the instruction holds for the session"


def test_a_request_for_tests_ends_the_session_waiver(session):
    session.prompt("Fix the paginate helper. Don't run the tests.")
    session.prompt("Thanks. Now add tests for paginate.")
    session.edit(COVERED)
    session.edit("tests/test_pagination.py", append="\n\ndef test_page_zero():\n    assert True\n")
    decision = session.stop()
    assert decision.action is DecisionAction.BLOCK
    assert "no tests were run" in decision.reason


def test_the_waiver_does_not_cross_sessions(repo):
    first, second = Session(repo, "s1"), None
    try:
        first.prompt("Fix the paginate helper. Don't run the tests.")
        second = Session.__new__(Session)
        second.repo, second.session_id, second.guard = repo, "s2", first.guard
        second.prompt("Fix the paginate helper.")
        second.edit(COVERED)
        assert second.stop().action is DecisionAction.BLOCK
    finally:
        first.close()


def test_probe_g_asks_for_tests_and_gets_held_until_they_exist(session):
    """Probe G: "…has no tests; fix it … and add tests" waived the gate. Now it is not
    a waiver, and a task asked for tests that writes none is not done."""
    session.prompt("The orders module has no tests; fix list_orders and add tests.")
    session.edit(UNTESTED)
    held = session.stop()
    assert held.action is DecisionAction.BLOCK
    assert "asked for tests" in held.reason
    assert any(f.subject == "requested-tests-missing" for f in held.findings)

    session.edit("tests/test_orders.py", append="from shop.api.orders import list_orders\n\n\n"
                 "def test_list_orders():\n    assert list_orders\n")
    session.run("pytest -q tests/test_orders.py", "1 passed in 0.01s\n")
    assert session.stop().action is DecisionAction.ALLOW
