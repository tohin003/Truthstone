"""The adapter, tested against payloads captured from a live Claude Code session.

Every other test in this suite feeds the adapter payloads *I* wrote, which means they
only ever test my reading of the documentation. That reading was wrong twice, and both
errors silently disabled an entire phase of work:

* the prompt arrives as ``prompt``; the docs say ``prompt_text``. The Intent Gateway was
  scoring an empty string on every real prompt, so Phase 2 did nothing in production.
* tool results arrive as ``tool_response``, a **dict**; the docs say ``tool_output``, a
  string. The Completion Gate never saw a test result, so Phase 4's central mechanism —
  catching an agent that claims passing tests it did not earn — never fired.

The fixtures in `tests/fixtures/hook_payloads/` are real payloads, captured by installing
a hook that dumps stdin and running `claude -p` against it. Paths and session ids are
scrubbed; the *shape* is untouched. Re-capture them whenever Claude Code changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from truthstone.adapters.claude_code import translate as claude
from truthstone.core.enums import EventType
from truthstone.verify import runners

PAYLOADS = Path(__file__).parent / "fixtures" / "hook_payloads"


def load(name: str) -> dict:
    return json.loads((PAYLOADS / f"{name}.json").read_text())


class TestCapturedPayloads:
    @pytest.mark.parametrize(
        "name",
        [
            "SessionStart",
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "Stop",
            "Stop.background_tasks",
        ],
    )
    def test_every_captured_event_translates(self, name):
        event = claude.to_event(load(name))
        assert event is not None, f"{name} did not translate"
        assert event.agent == "claude-code"
        assert event.workspace
        assert event.session_id

    def test_the_prompt_is_actually_read(self):
        """The bug: `prompt`, not `prompt_text`. Without this the whole Intent Gateway,
        Complexity Engine and Planning Governor operate on an empty string."""
        event = claude.to_event(load("UserPromptSubmit"))
        assert event.event is EventType.USER_PROMPT
        assert event.prompt_text, "the prompt must not be empty"
        assert "hello.py" in event.prompt_text

    def test_tool_arguments_are_read(self):
        event = claude.to_event(load("PreToolUse"))
        assert event.tool == "Write"
        assert event.arguments, "tool_input must survive translation"
        assert event.arg("file_path")

    def test_tool_results_are_read(self):
        """The other bug: `tool_response`, and it is a dict rather than a string."""
        event = claude.to_event(load("PostToolUse"))
        assert event.result is not None, "tool results must survive translation"
        text = runners.output_text(event.result)
        assert text, "the output text must be recoverable for test parsing"
        assert "test output here" in text

    def test_the_stop_payload_carries_its_loop_breaker(self):
        payload = load("Stop")
        event = claude.to_event(payload)
        assert event.last_assistant_message
        assert "stop_hook_active" in event.raw, "the gate's loop-safety flag must be present"

    def test_a_failing_run_arrives_as_post_tool_use_failure(self):
        """G1, captured live (2.1.317): an unpiped `pytest` that exits 1 is not a
        PostToolUse at all. Its output is in `error`, after an `Exit code 1` line."""
        payload = load("PostToolUseFailure")
        assert "tool_response" not in payload
        event = claude.to_event(payload)
        assert event.event is EventType.POST_TOOL_FAILURE
        assert event.result["exit_code"] == 1
        assert event.result["interrupted"] is False
        assert "1 failed, 1 passed" in event.result["stdout"]
        assert not event.result["stdout"].startswith("Exit code")

    def test_stop_reports_work_still_in_flight(self):
        """G7, captured live: a backgrounded shell is listed at Stop. Kept on `raw` for
        the core, which decides what an unfinished test run means."""
        event = claude.to_event(load("Stop.background_tasks"))
        task = event.raw["background_tasks"][0]
        assert task["type"] == "shell"
        assert task["status"] == "running"
        assert task["command"] == "sleep 25"
        assert event.raw["session_crons"] == []

    def test_a_background_task_notification_is_not_a_new_request(self):
        """Captured live: Claude Code reports a finished background task as a
        UserPromptSubmit. It must not open a new task (losing the running task's
        unverified edits) or earn a planning budget."""
        payload = load("UserPromptSubmit.task_notification")
        assert payload["prompt"].startswith("<task-notification>")
        assert claude.to_event(payload) is None
        assert claude.to_event(load("UserPromptSubmit")) is not None


class TestEndToEndWithRealShapes:
    def test_a_real_prompt_produces_a_real_planning_budget(self, workspace):
        """The regression that matters: a live prompt must reach the Intent Gateway."""
        from truthstone.core.config import Settings
        from truthstone.core.engine import Guard

        payload = {**load("UserPromptSubmit"), "cwd": str(workspace)}
        guard = Guard(Settings(profile="full"))
        try:
            guard.workspace(workspace).index.ready(timeout=30)
            decision = guard.handle(claude.to_event(payload))
            task = guard.workspace(workspace).store.recent_decisions(1)
        finally:
            guard.close()

        assert decision.additional_context, "a real prompt must produce a planning budget"
        assert "[Truthstone]" in decision.additional_context
        assert "complexity" in decision.additional_context
        assert task

    def test_a_real_failing_run_reaches_the_completion_gate(self, workspace):
        """The live PostToolUseFailure, end to end: the failure is recorded as a failed
        run, and a claimed completion afterwards is held."""
        from truthstone.core.config import Settings
        from truthstone.core.engine import Guard

        (workspace / "app.py").write_text("def helper(x):\n    return x * 2\n")
        (workspace / "tests").mkdir()
        (workspace / "tests" / "test_app.py").write_text(
            "from app import helper\n\n\ndef test_helper():\n    assert helper(2) == 5\n"
        )
        guard = Guard(Settings(profile="full"))
        try:
            guard.workspace(workspace).index.ready(timeout=30)

            def handle(payload, hook):
                event = claude.to_event({**payload, "cwd": str(workspace)})
                return claude.from_decision(event, guard.handle(event), hook)

            handle(load("UserPromptSubmit"), "UserPromptSubmit")
            edit = {
                **load("PostToolUse"),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(workspace / "app.py"), "old_string": "x", "new_string": "x"},
            }
            handle(edit, "PostToolUse")
            handle(load("PostToolUseFailure"), "PostToolUseFailure")
            held = handle(load("Stop"), "Stop")
        finally:
            guard.close()

        assert held["decision"] == "block"
        assert "verification_failed" in held["reason"]

    def test_a_piped_failing_run_arrives_as_post_tool_use(self, workspace):
        """`pytest -q | tail` exits with tail's status, so the failure comes as a normal
        PostToolUse with `tool_response` — the shape this test used to pin for every run."""
        payload = {
            **load("PostToolUse"),
            "cwd": str(workspace),
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q 2>&1 | tail -5"},
            "tool_response": {
                "stdout": "F.\n====== 1 failed, 1 passed in 0.2s ======\n",
                "stderr": "",
                "interrupted": False,
            },
        }
        event = claude.to_event(payload)
        outcome = runners.parse_output("pytest -q", runners.output_text(event.result))
        assert outcome.passed is False
        assert outcome.failed == 1
