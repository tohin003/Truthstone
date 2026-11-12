"""H1 — host capability profiles and the rendering ladder (``core/hosts.py``).

Three layers:

* the ladder itself, over every profile, every DecisionAction (with and without
  ``signoff_required``) and every phase: the properties that must hold everywhere;
* the binding cases: Codex sign-off deny, Codex advisory context, Claude ask, Claude
  MODIFY → ask with the updated arguments, Codex MODIFY → deny with the guarded form, an
  unknown host → CONSERVATIVE, never ``defer``;
* both adapters' wire output, pinned byte for byte in ``fixtures/hosts/rendering_golden.json``.
  Every output that H1 changed is listed in ``LADDER_CHANGES`` with the ladder rule that
  required it, and checked against that rule.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from tests.codex_schema import validate
from truthstone.adapters.claude_code import translate as claude
from truthstone.adapters.codex import render as codex_render
from truthstone.adapters.codex import translate as codex
from truthstone.core import hosts
from truthstone.core.enums import ChallengeCategory, DecisionAction, EventType, FailureMode, Severity, Verdict
from truthstone.core.models import Decision, Finding

A = DecisionAction
E = EventType
PROFILES = [hosts.CLAUDE_CODE, hosts.CODEX, hosts.CONSERVATIVE]
STOPS = (E.STOP, E.SUBAGENT_STOP)

RISK = Finding(
    category=ChallengeCategory.RISK,
    verdict=Verdict.REQUIRES_HUMAN,
    failure_mode=FailureMode.DESTRUCTIVE_ACTION,
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
    summary="Truthstone narrowed this command: guarded `OUT`",
    detail="`rm -rf $OUT` deletes `/` if `OUT` is empty. The rewrite refuses to run.",
)
GUARDED = '[ -n "$OUT" ] && rm -rf "$OUT"'


def matrix():
    """Every action, with and without sign-off, reason, context and rewritten arguments."""
    for action in DecisionAction:
        for signoff in (False, True):
            for reason in ("", "Truthstone — evidence check\n\nThe evidence."):
                for context in (None, "Extra context."):
                    for arguments in (None, {"command": GUARDED}):
                        yield Decision(
                            action=action,
                            reason=reason,
                            additional_context=context,
                            updated_arguments=arguments,
                            signoff_required=signoff,
                            findings=[RISK] if signoff else [GUARD],
                        )


# -- the ladder, everywhere ---------------------------------------------------------------


@pytest.mark.parametrize("phase", list(EventType))
@pytest.mark.parametrize("caps", PROFILES, ids=lambda caps: caps.name)
def test_the_ladder_holds_for_every_profile_action_and_phase(caps, phase):
    for decision in matrix():
        r = hosts.render(decision, caps, phase)
        assert r.kind in hosts.KINDS
        if r.kind in hosts.REASONED_KINDS:
            assert r.reason.strip(), (decision, r)
        if r.kind == "ask":
            assert caps.ask == "native" and phase is E.PRE_TOOL_USE
        if r.kind == "rewrite_ask":
            assert caps.rewrite == "with_user_approval" and caps.ask == "native"
            assert phase is E.PRE_TOOL_USE and decision.action is A.MODIFY
            assert r.updated_arguments == decision.updated_arguments
        if r.kind == "deny":
            assert phase is E.PRE_TOOL_USE and caps.can_block_pre
        if r.kind == "block":
            assert decision.action in (A.BLOCK, A.CHALLENGE)
            assert phase in (E.POST_TOOL_USE, E.USER_PROMPT, *STOPS)
        if r.kind == "context":
            assert caps.can_say(phase) or (phase is E.PRE_TOOL_USE and caps.can_say(E.POST_TOOL_USE))
        if r.expects_continuation:
            assert r.kind == "block" and phase in STOPS and caps.stop_continue == "new_prompt"
        if r.system_message:
            assert caps.system_message_visible
        if phase is E.SESSION_END or decision.action is A.ALLOW:
            assert r.kind in ("silent", "context") and not r.system_message

        review = decision.action is A.REQUEST_REVIEW
        if review and not decision.signoff_required:
            assert r.kind in ("ask", "context", "silent"), "an advisory review never blocks"
        if phase is E.PRE_TOOL_USE:
            if review and decision.signoff_required:
                if caps.ask == "native":
                    assert r.kind == "ask"
                else:
                    assert r.kind == "deny", "a sign-off never degrades where the host can deny"
                    assert r.reason.startswith(hosts.SIGNOFF_LEAD)
            if decision.action in (A.CHALLENGE, A.BLOCK):
                assert r.kind == "deny"
            if decision.action is A.MODIFY:
                reviewable = caps.rewrite == "with_user_approval" and decision.updated_arguments
                assert r.kind == ("rewrite_ask" if reviewable else "deny")
        if phase in STOPS and decision.action in (A.BLOCK, A.CHALLENGE):
            assert r.kind == "block"


def test_phases_are_accepted_by_value_and_unknown_ones_are_silent():
    decision = Decision(action=A.CHALLENGE, reason="no")
    assert hosts.render(decision, hosts.CODEX, "pre_tool_use").kind == "deny"
    assert hosts.render(decision, hosts.CODEX, "not-a-phase") is hosts.SILENT


# -- the binding cases ----------------------------------------------------------------------


def test_codex_signoff_is_a_deny_that_says_who_must_agree():
    decision = Decision(
        action=A.REQUEST_REVIEW,
        reason="Truthstone — evidence check\n\nIrreversible command: force push",
        findings=[RISK],
        signoff_required=True,
    )
    r = hosts.render(decision, hosts.CODEX, E.PRE_TOOL_USE)
    assert r.kind == "deny"
    # A1b: with no code nothing can grant it, so no re-run is promised (it used to be).
    assert r.reason.startswith("needs developer sign-off: ask the user to carry this out themselves")
    assert "re-run will be held again" in r.reason
    assert r.reason.endswith(decision.reason), "followed by the original reason"
    assert r.system_message == (
        "Truthstone is holding this for your sign-off: Irreversible command: force push"
    )

    # With a code (A1b) the developer can allow it once, and both are told how.
    coded = hosts.render(decision.model_copy(update={"signoff_code": "K7M2QX"}), hosts.CODEX, E.PRE_TOOL_USE)
    assert coded.kind == "deny"
    assert coded.reason.startswith(
        "needs developer sign-off: ask the user whether to go ahead. To allow it once, they reply "
        "`approve K7M2QX` or run `truthstone approve K7M2QX` in this project; then re-run it "
        "unchanged within 15 minutes."
    )
    assert coded.reason.endswith(decision.reason)
    assert coded.system_message == (
        "Truthstone is holding this for your sign-off: Irreversible command: force push. "
        "To allow it once, reply `approve K7M2QX` or run `truthstone approve K7M2QX`."
    )


def test_codex_advisory_review_is_non_blocking_context():
    decision = Decision(action=A.REQUEST_REVIEW, reason="Worth a second look.")
    for phase in (E.PRE_TOOL_USE, E.POST_TOOL_USE, E.USER_PROMPT):
        r = hosts.render(decision, hosts.CODEX, phase)
        assert (r.kind, r.context) == ("context", "Worth a second look.")
    assert hosts.render(decision, hosts.CODEX, E.STOP).is_silent, "Codex's Stop takes no context"


@pytest.mark.parametrize("signoff", [False, True])
@pytest.mark.parametrize("code", [None, "K7M2QX"])
def test_claude_review_is_a_native_ask(signoff, code):
    """The native ask is the sign-off: a code (A1b) is never shown there."""
    decision = Decision(
        action=A.REQUEST_REVIEW, reason="Force push.", signoff_required=signoff, signoff_code=code
    )
    r = hosts.render(decision, hosts.CLAUDE_CODE, E.PRE_TOOL_USE)
    assert (r.kind, r.reason, r.system_message) == ("ask", "Force push.", None)


def test_claude_modify_asks_with_the_updated_arguments():
    arguments = {"command": GUARDED}
    decision = Decision(
        action=A.MODIFY,
        reason=GUARD.summary,
        additional_context="Guarded the unset-variable delete.",
        updated_arguments=arguments,
        findings=[GUARD],
    )
    r = hosts.render(decision, hosts.CLAUDE_CODE, E.PRE_TOOL_USE)
    assert r.kind == "rewrite_ask"
    assert r.updated_arguments == arguments and r.updated_arguments is not arguments
    assert r.reason == r.context == "Guarded the unset-variable delete."
    spec = claude.from_decision(_claude_event("PreToolUse"), decision, "PreToolUse")["hookSpecificOutput"]
    assert (spec["permissionDecision"], spec["updatedInput"]) == ("ask", arguments)


def test_codex_modify_is_a_deny_showing_the_guarded_form():
    decision = Decision(
        action=A.MODIFY, reason=GUARD.summary, updated_arguments={"command": GUARDED}, findings=[GUARD]
    )
    r = hosts.render(decision, hosts.CODEX, E.PRE_TOOL_USE)
    assert r.kind == "deny"
    assert r.reason.startswith(f"{hosts.RISKY_LEAD} `rm -rf $OUT` deletes `/` if `OUT` is empty.")
    assert f"    {GUARDED}\n" in r.reason
    assert "narrowed" not in r.reason, "nothing was narrowed; the agent decides"


def test_codex_rewrite_switch_still_bypasses_nothing_but_the_rewrite():
    """`ENABLE_REWRITES` keeps working, stays off, and is never a grant on Codex."""
    assert codex_render.ENABLE_REWRITES is False
    assert hosts.CODEX.rewrite == "with_auto_approve" and not hosts.CODEX.allow_is_grant
    decision = Decision(action=A.MODIFY, reason="r", updated_arguments={"command": GUARDED})
    on = codex_render.render(_codex_event(), decision, "PreToolUse", rewrites=True)["hookSpecificOutput"]
    assert (on["permissionDecision"], on["updatedInput"]) == ("allow", {"command": GUARDED})
    granting = dataclasses.replace(hosts.CODEX, allow_is_grant=True)
    off = codex_render.render(_codex_event(), decision, "PreToolUse", caps=granting, rewrites=True)
    assert off["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("agent", ["cursor", "gemini-cli", "", None, "unknown"])
def test_an_unknown_host_gets_the_conservative_profile(agent):
    caps = hosts.capabilities_for(agent)
    assert caps is hosts.CONSERVATIVE
    signoff = Decision(action=A.REQUEST_REVIEW, reason="Force push.", findings=[RISK], signoff_required=True)
    assert hosts.render(signoff, caps, E.PRE_TOOL_USE).kind == "deny", "its ask is assumed to fail open"
    advisory = Decision(action=A.REQUEST_REVIEW, reason="Worth a look.")
    assert hosts.render(advisory, caps, E.PRE_TOOL_USE).is_silent, "no context channel is assumed"
    modify = Decision(action=A.MODIFY, reason="r", updated_arguments={"command": GUARDED}, findings=[GUARD])
    assert hosts.render(modify, caps, E.PRE_TOOL_USE).kind == "deny", "no rewrite is assumed"
    budget = Decision(additional_context="Complexity 3/100.")
    assert hosts.render(budget, caps, E.USER_PROMPT).is_silent
    gate = hosts.render(Decision(action=A.BLOCK, reason="Run the tests."), caps, E.STOP)
    assert gate.kind == "block" and not gate.expects_continuation and not gate.system_message


@pytest.mark.parametrize(("agent", "caps"), [("claude-code", hosts.CLAUDE_CODE), ("codex", hosts.CODEX),
                                             ("Claude_Code", hosts.CLAUDE_CODE), (" CODEX ", hosts.CODEX)])
def test_known_hosts_get_their_own_profile(agent, caps):
    assert hosts.capabilities_for(agent) is caps


def test_a_new_host_can_register_its_profile():
    caps = dataclasses.replace(hosts.CONSERVATIVE, name="test-host", ask="native")
    hosts.register_profile(caps)
    try:
        assert hosts.capabilities_for("test-host") is caps
    finally:
        hosts._PROFILES.pop("test-host", None)
    assert hosts.capabilities_for("test-host") is hosts.CONSERVATIVE


def test_the_profiles_say_what_the_hosts_were_verified_to_do():
    claude_caps, codex_caps = hosts.CLAUDE_CODE, hosts.CODEX
    assert (claude_caps.ask, codex_caps.ask) == ("native", "fails_open")
    assert (claude_caps.rewrite, codex_caps.rewrite) == ("with_user_approval", "with_auto_approve")
    assert (claude_caps.allow_is_grant, codex_caps.allow_is_grant) == (True, False)
    assert (claude_caps.stop_continue, codex_caps.stop_continue) == ("same_turn", "new_prompt")
    assert (claude_caps.failure_event, codex_caps.failure_event) == (True, False)
    assert (claude_caps.exit_code_in_result, codex_caps.exit_code_in_result) == (True, False)
    assert claude_caps.host_continuation_cap == 8
    assert codex_caps.context_channels == {"session_start", "user_prompt", "pre_tool_use", "post_tool_use"}
    assert claude_caps.context_channels == codex_caps.context_channels | {"post_tool_failure"}
    assert hosts.CONSERVATIVE.context_channels == frozenset()
    assert not hosts.CONSERVATIVE.system_message_visible


def test_stop_blocks_expect_a_continuation_only_where_it_arrives_as_a_prompt():
    gate = Decision(action=A.BLOCK, reason="Run the tests.")
    assert hosts.render(gate, hosts.CODEX, E.STOP).expects_continuation
    assert not hosts.render(gate, hosts.CLAUDE_CODE, E.STOP).expects_continuation


def test_never_defer_and_never_a_bare_grant_on_the_wire():
    """Whatever the core decides, neither adapter says "defer", and neither grants."""
    for decision in matrix():
        for hook in claude.EVENT_MAP:
            out = claude.from_decision(_claude_event(hook), decision, hook)
            text = json.dumps(out)
            assert '"defer"' not in text and '"allow"' not in text, out
        for hook in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"):
            for rewrites in (False, True):
                out = codex_render.render(_codex_event(), decision, hook, rewrites=rewrites)
                assert '"defer"' not in json.dumps(out), out
                spec = out.get("hookSpecificOutput", {})
                if spec.get("permissionDecision") == "allow":
                    assert rewrites and decision.action is A.MODIFY and spec["updatedInput"], out


def test_a_host_that_cannot_block_before_a_tool_is_told_in_context():
    no_deny = dataclasses.replace(hosts.CODEX, can_block_pre=False)
    challenge = Decision(action=A.CHALLENGE, reason="`get_user` does not exist.")
    r = hosts.render(challenge, no_deny, E.PRE_TOOL_USE)
    assert (r.kind, r.context) == ("context", "`get_user` does not exist.")
    post_only = dataclasses.replace(no_deny, context_channels=frozenset({E.POST_TOOL_USE}))
    assert hosts.render(challenge, post_only, E.PRE_TOOL_USE).kind == "context", "delivered after the call"
    mute = dataclasses.replace(no_deny, context_channels=frozenset())
    assert hosts.render(challenge, mute, E.PRE_TOOL_USE).is_silent, "record-only"


def test_a_host_that_cannot_continue_tells_the_developer_instead():
    stuck = dataclasses.replace(hosts.CLAUDE_CODE, stop_continue="none")
    gate = Decision(
        action=A.BLOCK,
        reason="Truthstone — completion gate: incomplete\n\n2 file(s) changed and no tests were run.",
        findings=[_gate_finding()],
    )
    r = hosts.render(gate, stuck, E.STOP)
    assert r.kind == "silent"
    assert r.system_message.startswith("Truthstone: this turn ended unverified — 2 file(s) changed")


class _FutureDecision(Decision):
    """``Decision.unverified_finish`` is being added by the core's completion-gate work."""

    unverified_finish: str | None = None


def test_an_unverified_finish_reaches_the_developer_where_it_can():
    decision = _FutureDecision(unverified_finish="2 file(s) changed and no tests were run")
    r = hosts.render(decision, hosts.CODEX, E.STOP)
    assert r.kind == "silent" and r.system_message.startswith(
        "Truthstone: this turn ended unverified — 2 file(s) changed and no tests were run."
    )
    out = codex.from_decision(_codex_event(), decision, "Stop")
    assert set(out) == {"systemMessage"} and validate(out, "stop.command.output") == []
    assert hosts.render(decision, hosts.CONSERVATIVE, E.STOP).is_silent, "nobody may be watching"
    assert hosts.render(Decision(), hosts.CODEX, E.STOP).is_silent


def test_rendering_refuses_shapes_no_host_may_receive():
    for kind in ("defer", "allow", "approve"):
        with pytest.raises(ValueError):
            hosts.Rendering(kind)
    with pytest.raises(ValueError):
        hosts.Rendering("deny", reason="  ")
    with pytest.raises(ValueError):
        hosts.Rendering("context")
    with pytest.raises(ValueError):
        hosts.Rendering("rewrite_ask", reason="r")
    with pytest.raises(ValueError):
        hosts.Rendering("deny", reason="r", updated_arguments={"command": "ls"})


def test_profiles_reject_values_they_do_not_know():
    with pytest.raises(ValueError):
        dataclasses.replace(hosts.CODEX, ask="sometimes")
    with pytest.raises(ValueError):
        dataclasses.replace(hosts.CODEX, context_channels=frozenset({"PostToolUse"}))


def test_claudes_rendering_profile_derives_from_the_core():
    assert isinstance(claude.CLAUDE, hosts.HostCapabilities)
    assert hosts.profile_fields(claude.CLAUDE) == hosts.profile_fields(hosts.CLAUDE_CODE)
    assert claude.CLAUDE.stop_block and claude.CLAUDE.system_message
    assert claude.MODIFY_PERMISSION == "ask"


def test_codexs_public_names_still_work():
    assert codex_render.CODEX_0_166 is hosts.CODEX
    assert codex_render.CodexCapabilities is hosts.HostCapabilities
    assert codex_render.SIGN_OFF == hosts.SIGNOFF_PREFIX
    assert codex_render.FALLBACK_REASON == hosts.FALLBACK_REASON


def test_codex_keeps_sign_off_for_a_review_that_lost_its_flag():
    """A decision merged from several (a multi-file patch) can lose ``signoff_required``;
    an irreversible RISK finding still holds it."""
    legacy = Decision(action=A.REQUEST_REVIEW, reason="Irreversible command: force push", findings=[RISK])
    spec = codex.from_decision(_codex_event(), legacy, "PreToolUse")["hookSpecificOutput"]
    assert spec["permissionDecision"] == "deny"
    assert spec["permissionDecisionReason"].startswith(hosts.SIGNOFF_PREFIX)


# -- the wire, byte for byte -----------------------------------------------------------------

GOLDEN = Path(__file__).parent / "fixtures" / "hosts" / "rendering_golden.json"

CASES = {
    "allow": Decision(),
    "allow+ctx": Decision(additional_context="Complexity 3/100."),
    "allow+blankctx": Decision(additional_context="  \n"),
    "challenge": Decision(action=A.CHALLENGE, reason="`get_user` does not exist."),
    "challenge+ctx": Decision(
        action=A.CHALLENGE, reason="`get_user` does not exist.", additional_context="ctx"
    ),
    "challenge-empty": Decision(action=A.CHALLENGE, reason=""),
    "block": Decision(action=A.BLOCK, reason="Truthstone — completion gate: incomplete\n\nRun the tests."),
    "block+ctx": Decision(action=A.BLOCK, reason="Broke the build.", additional_context="ctx"),
    "review-advisory": Decision(action=A.REQUEST_REVIEW, reason="Worth a second look."),
    "review-advisory+ctx": Decision(
        action=A.REQUEST_REVIEW, reason="Worth a second look.", additional_context="ctx"
    ),
    "review-risk-legacy": Decision(
        action=A.REQUEST_REVIEW, reason="Irreversible command: force push", findings=[RISK]
    ),
    "review-signoff": Decision(
        action=A.REQUEST_REVIEW,
        reason="Truthstone — evidence check\n\nIrreversible command: force push",
        findings=[RISK],
        signoff_required=True,
    ),
    # A1b: what the validator now emits — a sign-off with the code that allows it once.
    "review-signoff-code": Decision(
        action=A.REQUEST_REVIEW,
        reason="Truthstone — needs your sign-off\n\nIrreversible command: force push",
        findings=[RISK],
        signoff_required=True,
        signoff_code="K7M2QX",
    ),
    "modify": Decision(
        action=A.MODIFY,
        reason=GUARD.summary,
        additional_context=f"{GUARD.summary}. {GUARD.detail}",
        updated_arguments={"command": GUARDED},
        findings=[GUARD],
    ),
    "modify-noctx": Decision(action=A.MODIFY, reason="Narrowed.", updated_arguments={"command": GUARDED}),
    "modify-noargs": Decision(action=A.MODIFY, reason="use the helper", updated_arguments=None),
    "modify-empty": Decision(action=A.MODIFY, reason="", updated_arguments=None),
}
# Claude Code's Stop rendering (`_stop_out`) is not routed through the ladder in this change.
CLAUDE_HOOKS = [
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "SessionEnd"
]
CODEX_HOOKS = [
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStop", "SessionEnd"
]

# Every output H1 changed, relative to the adapters' own rendering at e087bf5, and the
# ladder rule that required it. Nothing a current core decision produces changed, except
# Codex's sign-off wording (the binding text). A1b changed that wording again: a sign-off
# with a code says how to allow it once; one without promises no re-run.
SIGNOFF_WORDING = "the sign-off deny now starts with the binding text"
SIGNOFF_CODE = "the sign-off deny names the code that allows it once, to the agent and the developer"
REVIEW_IS_CONTEXT = "an advisory review that cannot ask is non-blocking context: its reason, not nothing"
REASON_REQUIRED = "a deny or block always carries a reason (Codex already did; an empty one fails open)"
MODIFY_IS_A_CHALLENGE = "MODIFY with no reviewable rewrite is a CHALLENGE (Claude said nothing)"
BLANK_IS_ABSENT = "blank context is no context (Codex already did)"
_CODEX_PRE = (
    "codex|PreToolUse",
    "codex|PreToolUse:Write",
    "codex+rewrites|PreToolUse",
    "codex+rewrites|PreToolUse:Write",
)
LADDER_CHANGES = {
    **{
        f"{variant}|{case}": SIGNOFF_WORDING
        for variant in _CODEX_PRE
        for case in ("review-risk-legacy", "review-signoff")
    },
    **{f"{variant}|review-signoff-code": SIGNOFF_CODE for variant in _CODEX_PRE},
    **{
        f"claude-code|{hook}|{case}": REVIEW_IS_CONTEXT
        for hook in ("PostToolUse", "PostToolUseFailure", "UserPromptSubmit")
        for case in ("review-advisory", "review-advisory+ctx", "review-risk-legacy", "review-signoff")
    },
    "claude-code|PreToolUse|challenge-empty": REASON_REQUIRED,
    "claude-code|PostToolUse|challenge-empty": REASON_REQUIRED,
    "claude-code|PreToolUse|modify-noargs": MODIFY_IS_A_CHALLENGE,
    "claude-code|PreToolUse|modify-empty": MODIFY_IS_A_CHALLENGE,
    **{
        f"claude-code|{hook}|allow+blankctx": BLANK_IS_ABSENT
        for hook in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure")
    },
}


def _claude_event(hook: str):
    return claude.to_event(
        {"hook_event_name": hook, "cwd": "/tmp/ws", "session_id": "test-hosts", "tool_name": "Bash",
         "tool_input": {"command": "rm -rf $OUT"}}
    )


def _codex_event(tool: str = "Bash"):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "make build"}}
    return codex.to_event(payload).model_copy(update={"tool": tool})


def _gate_finding() -> Finding:
    return Finding(
        category=ChallengeCategory.TESTABILITY,
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        failure_mode=FailureMode.UNVERIFIED_CHANGE,
        subject="no-test-run",
        summary="2 file(s) changed and no tests were run.",
    )


def _wire(out: dict) -> str:
    """Exactly what the daemon's JSONResponse sends: insertion order, compact."""
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def wire_outputs() -> dict[str, str]:
    out: dict[str, str] = {}
    for case, decision in CASES.items():
        for hook in CLAUDE_HOOKS:
            rendered = claude.from_decision(_claude_event(hook), decision, hook)
            out[f"claude-code|{hook}|{case}"] = _wire(rendered)
        for hook in CODEX_HOOKS:
            out[f"codex|{hook}|{case}"] = _wire(codex.from_decision(_codex_event(), decision, hook))
        out[f"codex|PreToolUse:Write|{case}"] = _wire(
            codex.from_decision(_codex_event("Write"), decision, "PreToolUse")
        )
        for tool, suffix in (("Bash", ""), ("Write", ":Write")):
            rendered = codex_render.render(_codex_event(tool), decision, "PreToolUse", rewrites=True)
            out[f"codex+rewrites|PreToolUse{suffix}|{case}"] = _wire(rendered)
    return out


def write_golden() -> None:
    """Regenerate the pinned outputs after a deliberate rendering change (see README)."""
    GOLDEN.write_text(json.dumps(wire_outputs(), indent=0, sort_keys=True, ensure_ascii=False) + "\n")


def test_wire_output_is_pinned_byte_for_byte():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    current = wire_outputs()
    assert sorted(current) == sorted(golden)
    drifted = {key: (golden[key], current[key]) for key in golden if golden[key] != current[key]}
    assert not drifted, (
        "adapter output changed; if deliberate, justify it and run tests.test_hosts.write_golden():\n"
        + "\n".join(f"{k}\n  was {old}\n  now {new}" for k, (old, new) in drifted.items())
    )


@pytest.mark.parametrize("key", sorted(LADDER_CHANGES))
def test_each_change_h1_made_follows_its_ladder_rule(key):
    out = json.loads(json.loads(GOLDEN.read_text(encoding="utf-8"))[key])
    case = CASES[key.rsplit("|", 1)[1]]
    spec = out.get("hookSpecificOutput", {})
    rule = LADDER_CHANGES[key]
    # Every Codex deny ends in the adapter's one closing line (day 5, T5); the ladder's text precedes it.
    closing = f"\n\n{codex_render.CLOSING}" if key.startswith("codex") else ""
    if rule == SIGNOFF_WORDING:
        assert spec["permissionDecision"] == "deny"
        assert spec["permissionDecisionReason"] == f"{hosts.SIGNOFF_WITHOUT_CODE}\n\n{case.reason}{closing}"
    elif rule == SIGNOFF_CODE:
        lead = hosts.SIGNOFF_WITH_CODE.format(codes=case.signoff_code, minutes=15)
        assert spec["permissionDecision"] == "deny"
        assert spec["permissionDecisionReason"] == f"{lead}\n\n{case.reason}{closing}"
        assert out["systemMessage"].endswith(hosts.SIGNOFF_NOTICE_CODE.format(codes=case.signoff_code))
    elif rule == REVIEW_IS_CONTEXT:
        assert spec["additionalContext"] == case.reason and "decision" not in out
    elif rule == REASON_REQUIRED:
        assert hosts.FALLBACK_REASON in (spec.get("permissionDecisionReason"), out.get("reason"))
    elif rule == MODIFY_IS_A_CHALLENGE:
        assert spec["permissionDecision"] == "deny"
        assert spec["permissionDecisionReason"].startswith(hosts.RISKY_LEAD)
    else:
        assert rule == BLANK_IS_ABSENT and out == {}
