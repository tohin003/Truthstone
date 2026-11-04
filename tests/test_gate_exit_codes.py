"""G1: a test run's exit status leads, wherever the status is the runner's.

On Claude Code a non-zero Bash exit is not a PostToolUse at all: it arrives as
PostToolUseFailure with ``error = "Exit code N\\n<output>"``, which the adapter turns into
``{"stdout", "exit_code", "interrupted"}``. In the transcripts on this machine 281 of
2,561 real test runs (11%) arrived that way, and text parsing alone classified only 73
of them — so the status must decide first (docs/IMPROVEMENTS.md G1, Appendix A.1).

The status belongs to the runner only when nothing but ``&&`` follows it: ``pytest |
tail`` exits with tail's status, ``pytest; true`` with true's. There the text decides.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.adapters.codex import translate as codex
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.verify import runners

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS_DIR = FIXTURES / "runner_outputs"
CORPUS = [
    *json.loads((CORPUS_DIR / "real.json").read_text()),
    *json.loads((CORPUS_DIR / "reconstructed.json").read_text()),
]

PYTEST_FAIL = "F.\n=== FAILURES ===\nE   assert 1 == 2\n1 failed, 1 passed in 0.02s\n"
PYTEST_PASS = "..\n2 passed in 0.02s\n"
PYTEST_QQ_FAIL = ".F.   [100%]\n=== short test summary info ===\nFAILED tests/test_app.py::test_x - assert\n"


def outcome(command: str, stdout: str, exit_code: int | None = 0, interrupted: bool = False):
    return runners.outcome_from_result(
        command, {"stdout": stdout, "exit_code": exit_code, "interrupted": interrupted}
    )


class TestClassification:
    def test_a_non_test_command_is_not_an_outcome(self):
        assert outcome("grep -n pytest pyproject.toml", "12: pytest", 0) is None
        assert outcome("ls", "", 1) is None

    def test_the_status_fails_a_run_whose_text_has_no_summary(self):
        """`pytest -qq` prints no summary line; only the status says it failed."""
        result = outcome("pytest -qq", PYTEST_QQ_FAIL, 1)
        assert result.passed is False
        assert result.exit_code == 1
        assert "exit status 1" in result.summary

    def test_a_pipe_into_tail_is_judged_by_its_text(self):
        """The status is tail's (0); the failure is in the text."""
        assert outcome("pytest -q | tail -5", PYTEST_FAIL, 0).passed is False
        assert outcome("pytest -q 2>&1 | tail -5", PYTEST_PASS, 0).passed is True

    def test_semicolon_true_lets_the_text_decide(self):
        assert outcome("pytest -q; true", PYTEST_FAIL, 0).passed is False
        assert outcome("pytest -q; true", PYTEST_PASS, 0).passed is True
        assert outcome("pytest -q; false", PYTEST_PASS, 1).passed is True

    def test_an_or_chain_lets_the_text_decide(self):
        assert outcome("pytest -q || echo failed", PYTEST_FAIL + "failed\n", 0).passed is False

    def test_pytest_exit_5_is_not_a_failure(self):
        result = outcome("pytest -q", "no tests ran in 0.01s\n", 5)
        assert result.passed is None
        assert "no tests ran" in result.summary

    def test_an_interrupted_run_is_not_a_failure(self):
        result = outcome("pytest -q", "..\n!!! KeyboardInterrupt !!!\n", 130, interrupted=True)
        assert result.passed is None
        assert "interrupted" in result.summary
        # Claude Code's own PostToolUse shape for a stopped run
        legacy = runners.outcome_from_result("pytest -q", {"stdout": "..", "stderr": "", "interrupted": True})
        assert legacy.passed is None

    @pytest.mark.parametrize(
        ("command", "code", "passed"),
        [
            ("pytest", 1, False),
            ("pytest", 2, None),
            ("pytest", 3, None),
            ("pytest", 4, None),
            ("cargo test", 101, False),
            ("cargo nextest run", 100, False),
            ("go test ./...", 1, False),
            ("go test ./...", 2, False),  # the build failed
            ("npx mocha", 3, False),  # mocha exits with the number of failures
            ("npx jest", 1, False),
            ("npm test", 1, False),
            ("make test", 2, False),
            ("python -m unittest", 1, False),
            ("python -m unittest", 5, None),
            *[("pytest", code, None) for code in (124, 126, 127, 130, 137, 141, 143)],
            *[("npx jest", code, None) for code in (124, 127, 137, 143)],
        ],
    )
    def test_exit_status_table(self, command, code, passed):
        assert outcome(command, "", code).passed is passed

    def test_a_non_zero_status_never_passes(self):
        """pytest's 2 is also a KeyboardInterrupt, which still prints what ran so far."""
        assert outcome("pytest", "== 3 passed in 1.0s ==\n", 2).passed is None

    def test_a_non_zero_status_keeps_a_failure_the_text_shows(self):
        """pytest's 2 is also a collection error; the summary says `1 error`."""
        assert outcome("pytest", "== 1 error in 0.12s ==\n", 2).passed is False

    def test_an_unknown_status_leaves_the_text_to_decide(self):
        """Codex reports no status for Bash: `exit_code` is None."""
        assert outcome("pytest -q", PYTEST_FAIL, None).passed is False
        assert outcome("pytest -q", PYTEST_PASS, None).passed is True

    def test_plain_strings_and_legacy_dicts_still_work(self):
        assert runners.outcome_from_result("pytest -q", PYTEST_FAIL).passed is False
        legacy = {"stdout": PYTEST_PASS, "stderr": "", "interrupted": False, "isImage": False}
        assert runners.outcome_from_result("pytest -q", legacy).passed is True
        assert runners.outcome_from_result("pytest -q", {"exitCode": 1, "stdout": ""}).passed is False

    @pytest.mark.parametrize("case", CORPUS, ids=[case["id"] for case in CORPUS])
    def test_never_wrong_on_the_labelled_corpus(self, case):
        """D2's 104 outputs with their real exit statuses: a verdict may be missing,
        but it is never wrong."""
        result = runners.outcome_from_result(
            case["command"],
            {"stdout": case["stdout"], "stderr": case["stderr"], "exit_code": case["exit_code"]},
        )
        if result is None:  # not a recognised run (bazel, a custom script): no verdict
            return
        assert result.passed is None or result.passed == case["expected"], (case["id"], result.summary)

    def test_the_status_recovers_verdicts_the_text_cannot_give(self):
        verdicts = {
            case["id"]: runners.outcome_from_result(
                case["command"],
                {"stdout": case["stdout"], "stderr": case["stderr"], "exit_code": case["exit_code"]},
            )
            for case in CORPUS
        }
        assert verdicts["pytest-qq-fail"].passed is False  # no summary line; exit 1


# -- through the real adapters and Guard ----------------------------------------------------


def _load(directory: str, name: str) -> dict:
    return json.loads((FIXTURES / directory / f"{name}.json").read_text())


@pytest.fixture
def app(tmp_path) -> Path:
    root = tmp_path / "app"
    (root / "tests").mkdir(parents=True)
    (root / "app.py").write_text("def helper(x):\n    return x * 2\n")
    (root / "tests" / "test_app.py").write_text(
        "from app import helper\n\n\ndef test_helper():\n    assert helper(2) == 5\n"
    )
    return root


def _claude(guard: Guard, payload: dict, root: Path) -> dict:
    event = claude.to_event({**payload, "cwd": str(root)})
    return claude.from_decision(event, guard.handle(event), payload["hook_event_name"])


def _edit_app(root: Path) -> dict:
    return {
        **_load("hook_payloads", "PostToolUse"),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(root / "app.py"), "old_string": "x * 2", "new_string": "x * 2"},
    }


class TestThroughTheClaudeAdapter:
    def test_the_live_failure_blocks_a_claimed_pass_and_cites_the_command(self, app):
        guard = Guard(Settings())
        try:
            guard.workspace(app).index.ready(timeout=30)
            _claude(guard, _load("hook_payloads", "UserPromptSubmit"), app)
            _claude(guard, _edit_app(app), app)
            assert _claude(guard, _load("hook_payloads", "PostToolUseFailure"), app) == {}
            stop = {**_load("hook_payloads", "Stop"), "last_assistant_message": "Done - all tests pass."}
            held = _claude(guard, stop, app)
        finally:
            guard.close()
        assert held["decision"] == "block"
        assert "verification_failed" in held["reason"]
        assert "python3 -m pytest -q tests/test_app.py" in held["reason"]

    def test_a_failure_with_no_summary_is_still_a_failure(self, app):
        """Text alone would say "could not tell"; the exit status says failed."""
        failure = {**_load("hook_payloads", "PostToolUseFailure"), "error": "Exit code 1\n" + PYTEST_QQ_FAIL}
        failure["tool_input"] = {"command": "pytest -qq tests/test_app.py"}
        guard = Guard(Settings())
        try:
            ws = guard.workspace(app)
            ws.index.ready(timeout=30)
            _claude(guard, _load("hook_payloads", "UserPromptSubmit"), app)
            _claude(guard, _edit_app(app), app)
            _claude(guard, failure, app)
            state = ws.task_state(None, "sess-captured")
            held = _claude(guard, _load("hook_payloads", "Stop"), app)
        finally:
            guard.close()
        assert [o.passed for o in state.verification.outcomes] == [False]
        assert held["decision"] == "block"

    def test_a_powershell_failure_is_read_like_a_bash_one(self, app):
        failure = {**_load("hook_payloads", "PostToolUseFailure"), "tool_name": "PowerShell"}
        guard = Guard(Settings())
        try:
            ws = guard.workspace(app)
            ws.index.ready(timeout=30)
            _claude(guard, _load("hook_payloads", "UserPromptSubmit"), app)
            _claude(guard, failure, app)
            state = ws.task_state(None, "sess-captured")
        finally:
            guard.close()
        assert [o.passed for o in state.verification.outcomes] == [False]

    def test_an_interrupted_run_records_no_failure(self, app):
        stopped = {
            **_load("hook_payloads", "PostToolUseFailure"),
            "error": "Exit code 130\n..\n!!! KeyboardInterrupt !!!",
            "is_interrupt": True,
        }
        guard = Guard(Settings())
        try:
            ws = guard.workspace(app)
            ws.index.ready(timeout=30)
            _claude(guard, _load("hook_payloads", "UserPromptSubmit"), app)
            _claude(guard, stopped, app)
            state = ws.task_state(None, "sess-captured")
        finally:
            guard.close()
        assert state.verification.outcomes == []
        assert state.verification.commands_seen == ["python3 -m pytest -q tests/test_app.py"]


class TestThroughTheCodexAdapter:
    def test_a_failing_run_is_read_from_its_text(self, app):
        """Codex sends no exit status for Bash, so the output text decides."""
        base = {"session_id": "sess-codex", "cwd": str(app), "turn_id": "t1"}
        guard = Guard(Settings())
        try:
            ws = guard.workspace(app)
            ws.index.ready(timeout=30)
            codex.handle_payload(guard, {**_load("codex_payloads", "UserPromptSubmit"), **base})
            run = {
                **_load("codex_payloads", "PostToolUse.Bash"),
                **base,
                "tool_input": {"command": "pytest -q tests/test_app.py"},
                "tool_response": PYTEST_FAIL,
            }
            assert codex.handle_payload(guard, run) == {}
            state = ws.task_state(None, "sess-codex")
        finally:
            guard.close()
        assert [o.passed for o in state.verification.outcomes] == [False]
        assert state.verification.outcomes[0].exit_code is None
