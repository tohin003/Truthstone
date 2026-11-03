"""The Codex wire contract, checked against Codex's own generated schemas.

Two directions:

* every payload captured from a live ``codex exec`` (``fixtures/codex_payloads``) must
  validate against the vendored input schema for its event — so the fixtures really are
  what Codex 0.166.0 sends, and a re-capture after a Codex upgrade is checked too;
* every output the adapter can produce, for every decision action on every hook, must
  validate against the output schema. Codex rejects an output with any unknown field, and
  a rejected output fails *open*: the guard would silently stop guarding.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agentguard.adapters.codex import render
from agentguard.adapters.codex import translate as codex
from agentguard.core.enums import ChallengeCategory, DecisionAction, FailureMode, Severity, Verdict
from agentguard.core.models import Decision, Finding
from tests.codex_schema import validate

PAYLOADS = Path(__file__).parent / "fixtures" / "codex_payloads"


def schema_name(hook: str, direction: str) -> str:
    slug = re.sub(r"(?<!^)(?=[A-Z])", "-", hook).lower()
    return f"{slug}.command.{direction}"


def captured() -> list[Path]:
    return sorted(PAYLOADS.glob("*.json"))


@pytest.mark.parametrize("path", captured(), ids=lambda p: p.stem)
def test_captured_payloads_match_codex_input_schema(path):
    payload = json.loads(path.read_text())
    problems = validate(payload, schema_name(payload["hook_event_name"], "input"))
    assert problems == [], problems


def test_every_hook_we_install_was_captured_live():
    events = {json.loads(p.read_text())["hook_event_name"] for p in captured()}
    from agentguard.adapters.codex.install import HOOK_SPECS

    assert {spec.event for spec in HOOK_SPECS} <= events


RISK = Finding(
    category=ChallengeCategory.RISK,
    verdict=Verdict.REQUIRES_HUMAN,
    failure_mode=FailureMode.NOT_A_FAILURE,
    severity=Severity.HIGH,
    subject="git push --force",
    summary="Irreversible command: force push",
)
GUARD = Finding(
    category=ChallengeCategory.RISK,
    verdict=Verdict.SUPPORTED_WITH_RISK,
    failure_mode=FailureMode.NOT_A_FAILURE,
    severity=Severity.MEDIUM,
    subject="modified command",
    summary="AgentGuard narrowed this command",
    detail="`rm -rf $OUT` deletes `/` if `OUT` is empty. The rewrite refuses to run.",
)
DECISIONS = [
    Decision(),
    Decision(additional_context="Complexity 12/100. Plan: edit, test."),
    Decision(action=DecisionAction.CHALLENGE, reason="AgentGuard: `get_user` does not exist."),
    Decision(action=DecisionAction.BLOCK, reason="AgentGuard — completion gate: incomplete"),
    Decision(
        action=DecisionAction.REQUEST_REVIEW, reason="Irreversible command: force push", findings=[RISK]
    ),
    Decision(action=DecisionAction.REQUEST_REVIEW, reason="Worth a second look."),  # not irreversible
    Decision(
        action=DecisionAction.MODIFY,
        reason="narrowed",
        additional_context="AgentGuard narrowed this command.",
        updated_arguments={"command": '[ -n "$OUT" ] && rm -rf "$OUT"'},
        findings=[GUARD],
    ),
    Decision(action=DecisionAction.CHALLENGE, reason=""),  # an empty reason must still be valid
    Decision(action=DecisionAction.MODIFY, reason="", updated_arguments=None),
]


def bash(command: str = "make build"):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    return codex.to_event(payload)


@pytest.mark.parametrize("rewrites", [False, True], ids=["default", "rewrites-on"])
@pytest.mark.parametrize("hook", ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"])
@pytest.mark.parametrize("tool", ["Bash", "Write", "Delete"])
@pytest.mark.parametrize("decision", DECISIONS, ids=lambda d: f"{d.action}-{bool(d.reason)}")
def test_every_output_matches_codex_output_schema(hook, tool, decision, rewrites):
    event = bash().model_copy(update={"tool": tool})
    out = render.render(event, decision, hook, rewrites=rewrites)
    assert validate(out, schema_name(hook, "output")) == []


@pytest.mark.parametrize("decision", DECISIONS, ids=lambda d: f"{d.action}-{bool(d.reason)}")
def test_a_deny_or_block_always_carries_a_reason(decision):
    """Codex treats a deny/block with an empty reason as an invalid output: fail open."""
    event = bash()
    for hook in ("PreToolUse", "PostToolUse", "Stop", "UserPromptSubmit"):
        out = codex.from_decision(event, decision, hook)
        spec = out.get("hookSpecificOutput", {})
        if spec.get("permissionDecision") == "deny":
            assert spec["permissionDecisionReason"].strip()
        if out.get("decision") == "block":
            assert out["reason"].strip()


def test_the_validator_rejects_what_codex_rejects():
    """A validator that accepted everything would make the tests above meaningless."""
    stop_with_context = {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "x"}}
    assert validate(stop_with_context, "stop.command.output")
    assert validate({"permissionDecision": "deny"}, "pre-tool-use.command.output")
    defer = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "defer"}}
    assert validate(defer, "pre-tool-use.command.output")
    assert validate({"decision": "approve"}, "stop.command.output")


def test_session_end_output_is_always_empty():
    event = codex.to_event({"hook_event_name": "SessionEnd", "session_id": "s"})
    for decision in DECISIONS:
        assert codex.from_decision(event, decision, "SessionEnd") == {}
