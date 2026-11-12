"""Day 5, T5: acting on a guard hold costs the agent no extra model request.

In every recorded guarded cell where the guard spoke, the agent first opened the Codex plugin's
skill to learn how to answer: one extra request that re-sends the whole session. Two changes,
text only (no decision changes):

* every deny and hold the agent reads on Codex ends in one shared closing line,
  ``render.CLOSING``, added where Codex output is assembled (``adapters/codex/render.py``);
* the skill's listed description no longer offers to explain those messages, and says they are
  self-contained. Its body stays, as reference.

Claude Code's output is unchanged (its adapter does not take the line). Made-up names only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from truthstone.adapters.claude_code import translate as claude
from truthstone.adapters.codex import render
from truthstone.adapters.codex import translate as codex
from truthstone.core import hosts
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import ChallengeCategory, DecisionAction, EventType, FailureMode, Severity, Verdict
from truthstone.core.events import AgentEvent
from truthstone.core.models import Decision, Finding

SKILL = Path(__file__).resolve().parents[1] / "plugins" / "truthstone" / "skills" / "truthstone" / "SKILL.md"
SUFFIX = f"\n\n{render.CLOSING}"

RISK = Finding(
    category=ChallengeCategory.RISK,
    verdict=Verdict.REQUIRES_HUMAN,
    failure_mode=FailureMode.DESTRUCTIVE_ACTION,
    severity=Severity.CRITICAL,
    subject="git push --force",
    summary="Irreversible command: force push",
)


def _event(tool: str = "Bash", command: str = "make wren") -> AgentEvent:
    arguments = {"command": command} if tool == "Bash" else {"file_path": "/workspace/wren/nest.py"}
    return AgentEvent(
        event=EventType.PRE_TOOL_USE,
        agent="codex",
        workspace="/workspace",
        session_id="s",
        tool=tool,
        arguments=arguments,
    )


def _file(path: str) -> AgentEvent:
    return _event("Write").model_copy(update={"arguments": {"file_path": f"/workspace/{path}"}})


def _said(out: dict) -> str:
    """Everything in a Codex output the agent or the developer could read, as one string."""
    specific = out.get("hookSpecificOutput") or {}
    parts = [
        out.get("reason"),
        out.get("systemMessage"),
        specific.get("permissionDecisionReason"),
        specific.get("additionalContext"),
    ]
    return "\n".join(p for p in parts if isinstance(p, str))


def _interrupt(out: dict) -> str:
    """The reason of a deny or block; "" for anything else."""
    if out.get("decision") == "block":
        return out["reason"]
    specific = out.get("hookSpecificOutput") or {}
    return (
        specific.get("permissionDecisionReason", "") if specific.get("permissionDecision") == "deny" else ""
    )


# -- the line: once, last, on every deny and hold the agent reads ------------------------------------


def test_the_line_itself():
    """Pinned: it is sent once per hold, so its length is a cost (about 21 tokens)."""
    assert render.CLOSING == (
        "This message is complete: do what it asks, without working around it, then report the actual result."
    )
    assert "\n" not in render.CLOSING and len(render.CLOSING) <= 110


@pytest.mark.parametrize(
    ("hook", "decision"),
    [
        ("PreToolUse", Decision(action=DecisionAction.CHALLENGE, reason="`wren_nest` does not exist.")),
        ("PreToolUse", Decision(action=DecisionAction.BLOCK, reason="Blocked: `wren.lock` is generated.")),
        ("PostToolUse", Decision(action=DecisionAction.CHALLENGE, reason="A key was written to `wren.env`.")),
        (
            "Stop",
            Decision(
                action=DecisionAction.BLOCK, reason="Truthstone — completion gate: unverified\n\nRun it."
            ),
        ),
        ("SubagentStop", Decision(action=DecisionAction.BLOCK, reason="Run the wren tests.")),
    ],
)
def test_every_deny_and_hold_ends_with_the_line_once(hook, decision):
    out = codex.from_decision(_event(), decision, hook)
    reason = _interrupt(out)
    assert reason == decision.reason + SUFFIX
    assert _said(out).count(render.CLOSING) == 1


def test_a_sign_off_deny_ends_with_it_after_the_ladder_text():
    decision = Decision(
        action=DecisionAction.REQUEST_REVIEW, reason="Irreversible command: force push", findings=[RISK]
    )
    out = codex.from_decision(_event(command="git push --force"), decision, "PreToolUse")
    reason = _interrupt(out)
    assert reason.startswith(render.SIGN_OFF) and reason.endswith(SUFFIX)
    assert reason.count(render.CLOSING) == 1
    assert render.CLOSING not in out["systemMessage"]  # the developer's notice is not the agent's


def test_a_modify_shown_as_a_challenge_ends_with_it():
    decision = Decision(
        action=DecisionAction.MODIFY,
        reason="Truthstone narrowed this command.",
        updated_arguments={"command": '[ -n "$WREN" ] && rm -rf "$WREN"'},
    )
    reason = _interrupt(codex.from_decision(_event(command='rm -rf "$WREN"'), decision, "PreToolUse"))
    assert (
        reason.startswith(hosts.RISKY_LEAD) and reason.endswith(SUFFIX) and reason.count(render.CLOSING) == 1
    )


def test_an_empty_reason_still_says_who_objected_then_the_line():
    out = codex.from_decision(_event(), Decision(action=DecisionAction.BLOCK, reason=" "), "Stop")
    assert out == {"decision": "block", "reason": render.FALLBACK_REASON + SUFFIX}


def test_a_multi_file_patch_gets_one_line_for_all_its_concerns():
    results = [
        (_file("wren/nest.py"), Decision(action=DecisionAction.CHALLENGE, reason="`perch` does not exist.")),
        (_file("wren/egg.py"), Decision()),
        (_file("wren/song.py"), Decision(action=DecisionAction.CHALLENGE, reason="`trill` does not exist.")),
    ]
    event, decision = codex.combine(results)
    reason = _interrupt(codex.from_decision(event, decision, "PreToolUse"))
    assert reason.count(render.CLOSING) == 1 and reason.endswith(SUFFIX)
    assert reason.index("[wren/nest.py]") < reason.index("[wren/song.py]") < reason.index(render.CLOSING)


def test_a_reason_that_already_ends_with_it_is_not_doubled():
    decision = Decision(action=DecisionAction.BLOCK, reason="Run the wren tests." + SUFFIX)
    assert _interrupt(codex.from_decision(_event(), decision, "Stop")).count(render.CLOSING) == 1


# -- never on an allow, a silent answer, a note, or what only the developer reads ---------------------


HOOKS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "SessionEnd",
)


@pytest.mark.parametrize(
    "decision",
    [
        Decision(),
        Decision(additional_context="Complexity 3/100: a small change."),
        Decision(action=DecisionAction.REQUEST_REVIEW, reason="Worth a second look at `wren.cfg`."),
        Decision(unverified_finish="2 file(s) changed and no tests were run"),
        # Observe mode: what it would have done is recorded, nothing is said.
        Decision(would_have=DecisionAction.BLOCK, reason="Truthstone — completion gate: unverified"),
    ],
    ids=["allow", "context", "advisory-review", "unverified-notice", "observe"],
)
def test_never_on_anything_that_is_not_a_deny_or_hold(decision):
    for hook in HOOKS:
        out = codex.from_decision(_event(), decision, hook)
        assert _interrupt(out) == ""
        assert render.CLOSING not in _said(out), hook


def test_a_blocked_prompt_is_the_developers_to_read_and_gets_no_line():
    decision = Decision(action=DecisionAction.BLOCK, reason="Truthstone is switched off for this prompt.")
    out = codex.from_decision(_event(), decision, "UserPromptSubmit")
    assert out == {"decision": "block", "reason": decision.reason}


def test_a_rewrite_that_codex_applies_is_not_a_deny_and_gets_no_line():
    decision = Decision(
        action=DecisionAction.MODIFY,
        reason="Guarded the unset-variable delete.",
        updated_arguments={"command": '[ -n "$WREN" ] && rm -rf "$WREN"'},
    )
    out = render.render(_event(command='rm -rf "$WREN"'), decision, "PreToolUse", rewrites=True)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert render.CLOSING not in _said(out)


# -- the Claude Code host is unchanged ------------------------------------------------------------------


CLAUDE_HOOKS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop")


@pytest.mark.parametrize("action", list(DecisionAction))
def test_claude_code_output_is_unchanged_and_never_carries_the_line(action):
    """The line is Codex's (its skill listing caused the read); Claude Code still says exactly what the
    host-neutral ladder renders. ``test_hosts.py``'s byte-for-byte golden pins every Claude output too."""
    decision = Decision(
        action=action,
        reason="`wren_nest` does not exist.",
        findings=[RISK] if action is DecisionAction.REQUEST_REVIEW else [],
        updated_arguments={"command": "make wren"} if action is DecisionAction.MODIFY else None,
    )
    for hook in CLAUDE_HOOKS:
        event = claude.to_event(
            {
                "hook_event_name": hook,
                "cwd": "/tmp/wren",
                "session_id": "s",
                "tool_name": "Bash",
                "tool_input": {"command": "make wren"},
            }
        )
        out = claude.from_decision(event, decision, hook)
        assert render.CLOSING not in _said(out), (action, hook)
        rendering = hosts.render(decision, hosts.CLAUDE_CODE, claude_phase(hook))
        if rendering.kind in ("deny", "block") and _interrupt(out):
            assert _interrupt(out) == rendering.reason


def claude_phase(hook: str) -> EventType:
    return {
        "SessionStart": EventType.SESSION_START,
        "UserPromptSubmit": EventType.USER_PROMPT,
        "PreToolUse": EventType.PRE_TOOL_USE,
        "PostToolUse": EventType.POST_TOOL_USE,
        "PostToolUseFailure": EventType.POST_TOOL_FAILURE,
        "Stop": EventType.STOP,
    }[hook]


# -- through the daemon's path: a real Guard ------------------------------------------------------------


ASK = "wren already writes every chirp to the log when WREN_CHIRP_LOG=1 is set, so switch that on in CI."


def _repo(root: Path) -> Path:
    repo = root / "wren"
    files = {
        "wren/__init__.py": "",
        "wren/nest.py": "class Nest:\n    def add(self, twig):\n        return twig\n",
        "tests/test_nest.py": "from wren.nest import Nest\n\n\ndef test_add():\n    assert Nest().add(1)\n",
        ".github/workflows/ci.yml": "jobs:\n  smoke:\n    steps:\n      - run: python -m wren\n",
        "README.md": "# wren\n\nA small nest.\n",
    }
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return repo


def _payload(repo: Path, hook: str, **fields) -> dict:
    return {"session_id": "s", "turn_id": "t", "cwd": str(repo), "hook_event_name": hook, **fields}


def _ci_patch(repo: Path) -> dict:
    command = (
        "*** Begin Patch\n"
        f"*** Update File: {repo / '.github' / 'workflows' / 'ci.yml'}\n"
        "@@\n"
        "       - run: python -m wren\n"
        "+        env:\n"
        "+          WREN_CHIRP_LOG: '1'\n"
        "*** End Patch\n"
    )
    return {"command": command}


def test_through_the_engine_the_hold_carries_the_line_once_and_silence_stays_silent(tmp_path):
    repo = _repo(tmp_path)
    guard = Guard(Settings())
    try:
        guard.workspace(repo).index.ready(timeout=30)
        note, _r, _d = codex.dispatch(guard, _payload(repo, "UserPromptSubmit", prompt=ASK))
        read, _r, _d = codex.dispatch(
            guard, _payload(repo, "PreToolUse", tool_name="Bash", tool_input={"command": "cat README.md"})
        )
        held, _r, decision = codex.dispatch(
            guard, _payload(repo, "PreToolUse", tool_name="apply_patch", tool_input=_ci_patch(repo))
        )
        again, _r, _d = codex.dispatch(
            guard, _payload(repo, "PreToolUse", tool_name="apply_patch", tool_input=_ci_patch(repo))
        )
    finally:
        guard.close()
    assert note["hookSpecificOutput"]["additionalContext"] and render.CLOSING not in _said(note)  # a note
    assert read == {}  # silent
    reason = _interrupt(held)
    assert reason == decision.reason.strip() + SUFFIX  # the rule's own text, then the line, once
    assert "WREN_CHIRP_LOG" in reason and reason.count(render.CLOSING) == 1
    assert again == {}  # re-issued: proceeds, and says nothing


# -- the skill's listing -------------------------------------------------------------------------------


def _description() -> str:
    front = SKILL.read_text(encoding="utf-8").split("---")[1]
    match = re.search(r'^description: "(.*)"$', front, re.MULTILINE)
    assert match, "the description is one double-quoted line"
    return match.group(1)


def test_the_listing_no_longer_offers_to_explain_holds_and_says_messages_are_self_contained():
    description = _description()
    assert "self-contained" in description and "Not needed to act on its messages" in description
    assert not re.search(
        r"(?i)\b(explain\w*|resolve\w*|block\w*|held|hold\w*|denied|use when\w*)\b", description
    )


def test_the_listing_is_no_longer_than_the_one_it_replaced():
    """The listing goes with every request of every guarded session, silent or not: it may not grow.
    The replaced description was 106 characters (23 o200k tokens; this one is 22)."""
    assert len(_description()) <= 106


def test_the_body_stays_as_reference():
    body = SKILL.read_text(encoding="utf-8").split("---", 2)[2]
    for heading in (
        "## When a tool call is blocked",
        "## When the turn is kept open",
        "## Checking on Truthstone",
    ):
        assert heading in body
