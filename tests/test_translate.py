"""Claude Code adapter translation (SPEC §23)."""

from __future__ import annotations

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.core.enums import DecisionAction, EventType
from agentguard.core.models import Decision
from tests.conftest import pre_tool_use, session_start, stop_event, user_prompt_submit


class TestToEvent:
    def test_maps_every_subscribed_hook(self):
        for hook_name, expected in claude.EVENT_MAP.items():
            event = claude.to_event({"hook_event_name": hook_name, "cwd": "/tmp/ws"})
            assert event is not None, hook_name
            assert event.event is expected

    def test_ignores_unsubscribed_hooks(self):
        assert claude.to_event({"hook_event_name": "PreCompact"}) is None
        assert claude.to_event({}) is None

    def test_extracts_tool_call(self):
        event = claude.to_event(pre_tool_use("Edit", file_path="/tmp/ws/x.py", new_string="hello"))
        assert event.event is EventType.PRE_TOOL_USE
        assert event.agent == "claude-code"
        assert event.tool == "Edit"
        assert event.arg("new_string") == "hello"
        assert event.is_mutating
        assert not event.is_read_only

    def test_extracts_prompt(self):
        event = claude.to_event(user_prompt_submit("Add pagination to /users"))
        assert event.prompt_text == "Add pagination to /users"

    def test_read_only_tools_are_flagged(self):
        event = claude.to_event(pre_tool_use("Read", file_path="/tmp/ws/x.py"))
        assert event.is_read_only

    def test_keeps_raw_payload_for_lossless_round_trip(self):
        payload = stop_event(stop_hook_active=True)
        event = claude.to_event(payload)
        assert event.raw["stop_hook_active"] is True


class TestFromDecision:
    def test_allow_is_silent(self):
        """SPEC §39: normal operation produces no output at all."""
        event = claude.to_event(pre_tool_use())
        out = claude.from_decision(event, Decision.allow(), "PreToolUse")
        assert out == {}

    def test_agentguard_never_grants_permission(self):
        """A guard that auto-approves would override the developer's own permission rules.

        No decision path may ever emit permissionDecision == "allow".
        """
        event = claude.to_event(pre_tool_use())
        for action in DecisionAction:
            decision = Decision(action=action, reason="r", updated_arguments={"command": "ls"})
            out = claude.from_decision(event, decision, "PreToolUse")
            got = out.get("hookSpecificOutput", {}).get("permissionDecision")
            assert got != "allow", f"{action} produced permissionDecision=allow"

    def test_challenge_denies_with_reason(self):
        """SPEC §21: the reason goes back to the host, which re-reasons."""
        event = claude.to_event(pre_tool_use())
        decision = Decision(action=DecisionAction.CHALLENGE, reason="No such method exists.")
        out = claude.from_decision(event, decision, "PreToolUse")
        spec = out["hookSpecificOutput"]
        assert spec["hookEventName"] == "PreToolUse"
        assert spec["permissionDecision"] == "deny"
        assert spec["permissionDecisionReason"] == "No such method exists."

    def test_request_review_asks_the_human(self):
        event = claude.to_event(pre_tool_use())
        decision = Decision(action=DecisionAction.REQUEST_REVIEW, reason="Needs a human.")
        out = claude.from_decision(event, decision, "PreToolUse")
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_modify_rewrites_input_and_announces_itself(self):
        """SPEC §18 MODIFY. Silent rewrites would be a trust hazard, so it is announced —
        and the developer approves the narrowed input in their own permission prompt."""
        event = claude.to_event(pre_tool_use("Bash", command="rm -rf /"))
        decision = Decision(
            action=DecisionAction.MODIFY,
            reason="Narrowed to the intended directory.",
            updated_arguments={"command": "rm -rf ./build"},
        )
        out = claude.from_decision(event, decision, "PreToolUse")
        spec = out["hookSpecificOutput"]
        assert spec["updatedInput"] == {"command": "rm -rf ./build"}
        assert spec["permissionDecision"] == "ask"
        assert spec["permissionDecisionReason"], "the prompt must say why the input changed"
        assert spec["additionalContext"]

    def test_modify_never_defers(self):
        """A5. `defer` drops `updatedInput` and `additionalContext`, is ignored with a warning
        in interactive sessions, and ends a `-p` turn with the tool unrun (hooks docs,
        2.1.317: "For "defer", ignored"; "requires non-interactive mode")."""
        event = claude.to_event(pre_tool_use("Bash", command="rm -rf $OUT"))
        decision = Decision(
            action=DecisionAction.MODIFY,
            reason="Guarded the unset-variable delete.",
            updated_arguments={"command": '[ -n "$OUT" ] && rm -rf "$OUT"'},
        )
        spec = claude.from_decision(event, decision, "PreToolUse")["hookSpecificOutput"]
        assert spec["permissionDecision"] not in claude.FORBIDDEN_PERMISSIONS
        assert claude.MODIFY_PERMISSION == "ask"

    def test_user_prompt_injects_context(self):
        """SPEC §9/§13: the planning budget rides in on additionalContext."""
        event = claude.to_event(user_prompt_submit("Rename getUser"))
        decision = Decision(additional_context="Complexity: 2/100. Plan: find refs, rename, test.")
        out = claude.from_decision(event, decision, "UserPromptSubmit")
        assert "Complexity: 2/100" in out["hookSpecificOutput"]["additionalContext"]

    def test_stop_block_is_the_completion_gate(self):
        """SPEC §19: a blocked Stop forces the agent to keep working."""
        event = claude.to_event(stop_event())
        decision = Decision(action=DecisionAction.BLOCK, reason="No tests were run.")
        out = claude.from_decision(event, decision, "Stop")
        assert out == {"decision": "block", "reason": "No tests were run."}

    def test_post_tool_use_block(self):
        event = claude.to_event(pre_tool_use())
        decision = Decision(action=DecisionAction.BLOCK, reason="Broke the build.")
        out = claude.from_decision(event, decision, "PostToolUse")
        assert out["decision"] == "block"
        assert out["reason"] == "Broke the build."

    def test_session_start_context(self):
        event = claude.to_event(session_start())
        out = claude.from_decision(event, Decision(additional_context="1200 files indexed."), "SessionStart")
        assert out["hookSpecificOutput"]["additionalContext"] == "1200 files indexed."

    @pytest.mark.parametrize(
        "hook_name", ["PreToolUse", "PostToolUse", "Stop", "UserPromptSubmit", "SessionStart"]
    )
    def test_silence_for_every_hook_on_plain_allow(self, hook_name):
        event = claude.to_event(pre_tool_use())
        assert claude.from_decision(event, Decision.allow(), hook_name) == {}


# -- G1 · failing runs arrive as PostToolUseFailure -----------------------------------------


@pytest.fixture(autouse=True)
def _fresh_session_modes():
    claude.reset_session_modes()
    yield
    claude.reset_session_modes()


def post_tool_use_failure(command: str, error: str, interrupt: bool = False) -> dict:
    """The documented shape (hooks reference, 2.1.317): no `tool_response`, an `error`."""
    return {
        "session_id": "sess-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/tmp/ws",
        "permission_mode": "default",
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "Run tests"},
        "tool_use_id": "toolu_fail",
        "error": error,
        "is_interrupt": interrupt,
        "duration_ms": 1234,
    }


class TestPostToolUseFailure:
    def test_a_failing_run_carries_exit_code_and_output(self):
        event = claude.to_event(
            post_tool_use_failure("pytest -q", "Exit code 1\nF.\n1 failed, 1 passed in 0.02s")
        )
        assert event.event is EventType.POST_TOOL_FAILURE
        assert event.tool == "Bash"
        assert event.arg("command") == "pytest -q"
        assert event.result == {
            "stdout": "F.\n1 failed, 1 passed in 0.02s",
            "exit_code": 1,
            "interrupted": False,
        }

    def test_an_interrupt_is_reported_as_such(self):
        event = claude.to_event(post_tool_use_failure("pytest", "Exit code 130\n^C", interrupt=True))
        assert event.result["interrupted"] is True
        assert event.result["exit_code"] == 130

    def test_a_failure_without_an_exit_line_keeps_the_whole_message(self):
        """Claude Code could not start the shell at all: no exit code, no guessing."""
        event = claude.to_event(post_tool_use_failure("pytest", "spawn /bin/zsh ENOENT"))
        assert event.result == {"stdout": "spawn /bin/zsh ENOENT", "exit_code": None, "interrupted": False}

    def test_a_missing_error_is_harmless(self):
        payload = post_tool_use_failure("pytest", "")
        del payload["error"]
        event = claude.to_event(payload)
        assert event.result["exit_code"] is None
        assert event.result["stdout"] == ""

    def test_the_failure_reaches_the_test_record_of_todays_core(self):
        """Compatibility with the current core: a dict with `exit_code` is read as a run."""
        from agentguard.verify import runners

        event = claude.to_event(
            post_tool_use_failure("pytest -q", "Exit code 1\nF.\n1 failed, 1 passed in 0.02s")
        )
        outcome = runners.parse_output("pytest -q", runners.output_text(event.result))
        assert outcome.passed is False
        assert outcome.failed == 1

    def test_post_tool_use_failure_never_emits_a_block(self):
        """The event takes `additionalContext` only; an objection travels as context."""
        event = claude.to_event(post_tool_use_failure("pytest", "Exit code 1\nboom"))
        for action in DecisionAction:
            out = claude.from_decision(
                event, Decision(action=action, reason="objection"), "PostToolUseFailure"
            )
            assert "decision" not in out, action
        out = claude.from_decision(
            event, Decision(action=DecisionAction.BLOCK, reason="objection"), "PostToolUseFailure"
        )
        assert out["hookSpecificOutput"]["additionalContext"] == "objection"


# -- never grant, never defer --------------------------------------------------------------


@pytest.mark.parametrize("hook_name", list(claude.EVENT_MAP))
@pytest.mark.parametrize("action", list(DecisionAction))
def test_no_rendering_grants_or_defers(hook_name, action):
    """Whatever the core decides, Claude Code is never told "allow" or "defer"."""
    event = claude.to_event({"hook_event_name": hook_name, "cwd": "/tmp/ws", "session_id": "s"})
    decision = Decision(
        action=action,
        reason="r",
        additional_context="c",
        updated_arguments={"command": "ls"},
    )
    out = claude.from_decision(event, decision, hook_name)
    text = repr(out)
    assert "'allow'" not in text and "'defer'" not in text, out
    assert out.get("decision") in (None, "block")


# -- G10 · the completion gate gives up, the developer hears it ------------------------------


def _gate_finding(mode=None, severity=None):
    from agentguard.core.enums import ChallengeCategory, FailureMode, Severity, Verdict
    from agentguard.core.models import Finding

    return Finding(
        category=ChallengeCategory.TESTABILITY,
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        failure_mode=mode or FailureMode.UNVERIFIED_CHANGE,
        severity=severity or Severity.MEDIUM,
        subject="no-test-run",
        summary="2 file(s) changed and no tests were run",
    )


class TestGateGaveUp:
    def test_a_muted_gate_tells_the_developer(self):
        event = claude.to_event(stop_event(stop_hook_active=True))
        decision = Decision(action=DecisionAction.ALLOW, findings=[_gate_finding()])
        out = claude.from_decision(event, decision, "Stop")
        assert set(out) == {"systemMessage"}
        assert "2 file(s) changed and no tests were run" in out["systemMessage"]
        assert "decision" not in out, "it informs; it does not hold the turn again"

    def test_observe_mode_stays_silent(self):
        """`observe.silence()` keeps findings for the census and sets `would_have`."""
        from agentguard.core.observe import silence

        event = claude.to_event(stop_event())
        blocked = Decision(action=DecisionAction.BLOCK, reason="r", findings=[_gate_finding()])
        assert claude.from_decision(event, silence(blocked), "Stop") == {}

    def test_informational_findings_are_not_a_give_up(self):
        from agentguard.core.enums import FailureMode, Severity

        event = claude.to_event(stop_event())
        quiet = Decision(
            action=DecisionAction.ALLOW,
            findings=[_gate_finding(FailureMode.INSUFFICIENT_TESTS, Severity.INFO)],
        )
        assert claude.from_decision(event, quiet, "Stop") == {}

    def test_through_the_real_guard(self, workspace):
        """Block once, then the agent stops again without running tests: the gate is muted
        by its own loop safety, and the developer is told the turn ended unverified."""
        from agentguard.core.config import Settings
        from agentguard.core.engine import Guard

        (workspace / "app.py").write_text("def add(a, b):\n    return a + b\n")
        (workspace / "tests").mkdir()
        (workspace / "tests" / "test_app.py").write_text(
            "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        )
        guard = Guard(Settings())
        try:
            guard.workspace(workspace).index.ready(timeout=30)

            def handle(payload, hook):
                event = claude.to_event({**payload, "cwd": str(workspace)})
                return claude.from_decision(event, guard.handle(event), hook)

            handle(user_prompt_submit("Make add() return an int"), "UserPromptSubmit")
            edit = {
                **pre_tool_use(
                    "Edit",
                    file_path=str(workspace / "app.py"),
                    old_string="a + b",
                    new_string="int(a + b)",
                ),
                "hook_event_name": "PostToolUse",
                "tool_response": {"filePath": str(workspace / "app.py")},
            }
            handle(edit, "PostToolUse")
            first = handle(stop_event("Done."), "Stop")
            second = handle(stop_event("Done.", stop_hook_active=True), "Stop")
        finally:
            guard.close()

        assert first.get("decision") == "block"
        assert "systemMessage" in second and "unverified" in second["systemMessage"]


# -- R10 · per-session DISABLE and OBSERVE ---------------------------------------------------


class TestSessionModes:
    def test_registration_is_consumed_by_the_adapter(self):
        message = claude.session_mode_message("sess-1", "disabled")
        assert claude.to_event(message) is None
        assert claude.session_mode("sess-1") == "disabled"

    def test_a_disabled_session_never_reaches_the_core(self):
        claude.to_event(claude.session_mode_message("sess-1", "disabled"))
        assert claude.to_event(pre_tool_use("Bash", command="git push --force origin main")) is None
        other = {**pre_tool_use("Bash", command="ls"), "session_id": "sess-2"}
        assert claude.to_event(other) is not None, "other sessions are untouched"

    def test_an_observed_session_is_judged_but_hears_nothing(self):
        claude.to_event(claude.session_mode_message("sess-1", "observe"))
        event = claude.to_event(pre_tool_use("Bash", command="git push --force origin main"))
        assert event is not None, "observe still records"
        decision = Decision(action=DecisionAction.REQUEST_REVIEW, reason="force push")
        assert claude.from_decision(event, decision, "PreToolUse") == {}

    def test_session_end_forgets_the_mode(self):
        claude.to_event(claude.session_mode_message("sess-1", "observe"))
        end = claude.to_event({"hook_event_name": "SessionEnd", "session_id": "sess-1", "cwd": "/tmp"})
        claude.from_decision(end, Decision.allow(), "SessionEnd")
        assert claude.session_mode("sess-1") == "guard"

    def test_guard_mode_clears_a_previous_mode(self):
        claude.to_event(claude.session_mode_message("sess-1", "observe"))
        claude.to_event(claude.session_mode_message("sess-1", "guard"))
        assert claude.session_mode("sess-1") == "guard"

    def test_unknown_modes_are_ignored(self):
        claude.to_event(claude.session_mode_message("sess-1", "nonsense"))
        assert claude.session_mode("sess-1") == "guard"
