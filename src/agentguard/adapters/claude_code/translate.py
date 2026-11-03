"""Claude Code ⇄ AgentGuard translation (SPEC §23, §26).

    "Every adapter translates its native events into this common representation."

This module is the *only* place in the codebase that knows Claude Code's JSON shape, and
every decision about how a core ``Decision`` is *rendered* for Claude Code lives in one
object, :data:`CLAUDE`, so a host-capability profile can replace it wholesale.

A safety property worth stating explicitly
------------------------------------------
**AgentGuard never emits ``permissionDecision: "allow"``.**

"allow" short-circuits the developer's own permission rules, so a guard layer that used it
would make the system *less* safe. Every path therefore only ever: stays silent (no
decision — the normal permission flow proceeds), objects (``"deny"`` with a reason the host
can reason about), or escalates to the human (``"ask"``).

MODIFY — a proven narrowing rewrite — is rendered as ``"ask"`` plus ``updatedInput``: the
developer sees the narrowed command in their permission prompt and approves it. It was
first shipped as ``"defer"``, which Claude Code's documentation and source both rule out:
``defer`` drops ``updatedInput`` and ``additionalContext``, is ignored with a warning in
interactive sessions, and *ends the turn* in ``-p`` runs ("tool_deferred"). It must never
be emitted.

Hook contract re-verified against https://code.claude.com/docs/en/hooks on 2026-11-04
(Claude Code 2.1.317) and against captured live payloads in ``tests/fixtures/``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentguard.adapters.claude_code.protocol import (
    SESSION_MODE_EVENT,
    SESSION_MODE_FIELD,
    SESSION_MODES,
    session_mode_message,
)
from agentguard.core.enums import DecisionAction, EventType, FailureMode, Severity
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision

__all__ = [
    "CLAUDE",
    "EVENT_MAP",
    "MODIFY_PERMISSION",
    "SESSION_MODE_EVENT",
    "SESSION_MODE_FIELD",
    "SUBSCRIBED_EVENTS",
    "failure_result",
    "from_decision",
    "gate_gave_up",
    "session_mode",
    "session_mode_message",
    "to_event",
]

AGENT_NAME = "claude-code"


@dataclass(frozen=True)
class ClaudeRendering:
    """How each core intent is expressed to Claude Code. The one place to change it.

    ``docs/ADAPTER-CONTRACT.md`` calls this a host-capability profile: the core states
    intent (a ``Decision``); the profile says which native channel carries it.
    """

    # PreToolUse ``permissionDecision`` per intent. Never "allow" (AgentGuard does not
    # grant permissions) and never "defer" (see the module docstring).
    deny: str = "deny"  # CHALLENGE / BLOCK: the reason goes back to Claude
    review: str = "ask"  # REQUEST_REVIEW: the developer's own permission prompt
    rewrite: str = "ask"  # MODIFY: ``updatedInput`` + ask, the developer approves it
    # Stop / SubagentStop: ``decision: "block"`` keeps the turn going (Claude Code caps
    # consecutive continuations at 8; AgentGuard's own cap is lower).
    stop_block: bool = True
    # The universal ``systemMessage`` field: shown to the developer, never to Claude.
    system_message: bool = True
    # Events that accept ``decision: "block"`` after a tool ran. PostToolUseFailure does
    # not: it takes ``additionalContext`` only.
    post_tool_block_events: tuple[str, ...] = ("PostToolUse",)


CLAUDE = ClaudeRendering()

# Kept as a module constant: tests and callers assert against it.
MODIFY_PERMISSION = CLAUDE.rewrite
FORBIDDEN_PERMISSIONS = frozenset({"allow", "defer"})

# Claude Code hook event name -> normalized event type.
EVENT_MAP: dict[str, EventType] = {
    "SessionStart": EventType.SESSION_START,
    "UserPromptSubmit": EventType.USER_PROMPT,
    "PreToolUse": EventType.PRE_TOOL_USE,
    "PostToolUse": EventType.POST_TOOL_USE,
    "PostToolUseFailure": EventType.POST_TOOL_FAILURE,
    "Stop": EventType.STOP,
    "SubagentStop": EventType.SUBAGENT_STOP,
    "SessionEnd": EventType.SESSION_END,
}

# The events AgentGuard asks to be installed for. Anything else is noise.
SUBSCRIBED_EVENTS: tuple[str, ...] = tuple(EVENT_MAP)

# A Bash or PowerShell failure's ``error`` starts with this line (hooks docs, 2.1.317).
_EXIT_LINE = re.compile(r"^\s*Exit code (-?\d+)\s*$")


# -- per-session modes (R10) ---------------------------------------------------------------
#
# ``AGENTGUARD_DISABLE=1 claude`` and ``AGENTGUARD_OBSERVE=1 claude`` are per-session
# switches, but the daemon is shared and reads its own environment once, so a session's
# http hooks used to be guarded regardless. The command hooks *do* see the session's
# environment; they report it with a registration message, and this registry — which
# lives in the daemon process, where every hook request is translated — applies it:
#
# * disabled: every event of that session translates to ``None`` (the core never sees it);
# * observe:  events are judged and recorded, but nothing is rendered back.
#
# The core half (observe accounting without side effects, persistence across a daemon
# restart) belongs to the core; the command hooks re-register on every prompt meanwhile.

_MAX_TRACKED_SESSIONS = 4096
_session_modes: dict[str, str] = {}


def session_mode(session_id: str) -> str:
    return _session_modes.get(session_id, "guard")


def _note_session_mode(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    mode = payload.get(SESSION_MODE_FIELD)
    if not isinstance(session_id, str) or not session_id or mode not in SESSION_MODES:
        return
    if mode == "guard":
        _session_modes.pop(session_id, None)
        return
    if len(_session_modes) >= _MAX_TRACKED_SESSIONS and session_id not in _session_modes:
        _session_modes.pop(next(iter(_session_modes)))  # oldest first: dicts keep order
    _session_modes[session_id] = mode


def reset_session_modes() -> None:
    """For tests."""
    _session_modes.clear()


# -- inbound -------------------------------------------------------------------------------


def failure_result(payload: dict[str, Any]) -> dict[str, Any]:
    """``PostToolUseFailure`` -> the tool-result dict the core reads.

    A non-zero Bash exit never arrives as ``PostToolUse``: Claude Code reports it as
    ``PostToolUseFailure`` with ``error = "Exit code N\\n<interleaved output>"`` and no
    ``tool_response``. Contract (``docs/ADAPTER-CONTRACT.md``):

        {"stdout": <output without the exit line>, "exit_code": N | None,
         "interrupted": bool}

    ``exit_code`` is ``None`` when there is no exit line — Claude Code could not start the
    shell at all, or the tool is not a shell.
    """
    error = payload.get("error")
    text = error if isinstance(error, str) else ""
    first, _, rest = text.partition("\n")
    match = _EXIT_LINE.match(first)
    return {
        "stdout": rest if match else text,
        "exit_code": int(match.group(1)) if match else None,
        "interrupted": bool(payload.get("is_interrupt")),
    }


def to_event(payload: dict[str, Any]) -> AgentEvent | None:
    """Claude Code hook payload -> AgentEvent. Returns None for events we ignore.

    Field names here are taken from **captured live payloads**
    (`tests/fixtures/hook_payloads/`), not from the documentation. Two of them differ,
    and both differences silently disabled a whole phase of work:

    * the prompt arrives as ``prompt``, not ``prompt_text`` — the documented name — so
      the Intent Gateway was scoring an empty string on every real prompt;
    * tool results arrive as ``tool_response``, not ``tool_output``, and as a *dict*
      rather than a string — so the Completion Gate never saw a single test result.

    Both documented names are still accepted, in case they are version-dependent. A third
    shape, ``PostToolUseFailure``, carries a failing run's output in ``error``; see
    :func:`failure_result`.
    """
    hook_name = payload.get("hook_event_name", "")
    if hook_name == SESSION_MODE_EVENT:
        _note_session_mode(payload)
        return None
    event_type = EVENT_MAP.get(hook_name)
    if event_type is None:
        return None

    session_id = payload.get("session_id") or ""
    _note_session_mode(payload)
    if session_mode(session_id) == "disabled":
        if event_type is EventType.SESSION_END:
            _session_modes.pop(session_id, None)
        return None

    if event_type is EventType.POST_TOOL_FAILURE:
        result: Any = failure_result(payload)
    else:
        result = payload.get("tool_response", payload.get("tool_output"))

    return AgentEvent(
        event=event_type,
        agent=AGENT_NAME,
        workspace=payload.get("cwd") or ".",
        session_id=session_id,
        tool=payload.get("tool_name"),
        arguments=payload.get("tool_input") or {},
        tool_use_id=payload.get("tool_use_id"),
        result=result,
        prompt_text=payload.get("prompt") or payload.get("prompt_text"),
        last_assistant_message=payload.get("last_assistant_message"),
        raw=payload,
    )


# -- outbound ------------------------------------------------------------------------------


def _spec_out(hook_name: str, **fields: Any) -> dict[str, Any]:
    body = {"hookEventName": hook_name}
    body.update({k: v for k, v in fields.items() if v is not None})
    return {"hookSpecificOutput": body}


def from_decision(event: AgentEvent, decision: Decision, hook_name: str) -> dict[str, Any]:
    """Decision -> Claude Code hook output JSON.

    An empty dict means "AgentGuard has no opinion", which is the desired outcome for
    the overwhelming majority of actions (SPEC §39).
    """
    if session_mode(event.session_id) == "observe":
        out: dict[str, Any] = {}  # judged and recorded; nothing said (R10)
    elif hook_name == "PreToolUse":
        out = _pre_tool_use_out(decision)
    elif hook_name in ("PostToolUse", "PostToolUseFailure"):
        out = _post_tool_use_out(decision, hook_name)
    elif hook_name == "UserPromptSubmit":
        out = _context_only_out(decision, hook_name)
    elif hook_name in ("Stop", "SubagentStop"):
        out = _stop_out(decision, hook_name)
    elif hook_name == "SessionStart":
        out = _session_start_out(decision)
    else:
        out = {}

    if event.event is EventType.SESSION_END:
        _session_modes.pop(event.session_id, None)
    return out


def _pre_tool_use_out(decision: Decision) -> dict[str, Any]:
    action = decision.action

    if action in (DecisionAction.CHALLENGE, DecisionAction.BLOCK):
        # "deny" hands the reason back to Claude, which then re-reasons with its own
        # intelligence and proposes something else (SPEC §21). This *is* the loop.
        return _spec_out(
            "PreToolUse",
            permissionDecision=CLAUDE.deny,
            permissionDecisionReason=decision.reason,
        )

    if action is DecisionAction.REQUEST_REVIEW:
        # "ask": the reason is shown to the developer in the permission prompt. In a
        # `-p` run where nobody can answer, Claude Code denies the call and Claude reads
        # the same reason in the tool result.
        return _spec_out(
            "PreToolUse",
            permissionDecision=CLAUDE.review,
            permissionDecisionReason=decision.reason,
        )

    if action is DecisionAction.MODIFY and decision.updated_arguments is not None:
        # The rewrite always announces itself — silently changing what the agent asked
        # for is a trust hazard even when the change is an improvement — and it is never
        # approved on the developer's behalf: "ask" shows them the narrowed input.
        announcement = decision.additional_context or decision.reason or None
        return _spec_out(
            "PreToolUse",
            permissionDecision=CLAUDE.rewrite,
            permissionDecisionReason=announcement,
            updatedInput=decision.updated_arguments,
            additionalContext=announcement,
        )

    if decision.additional_context:
        return _spec_out("PreToolUse", additionalContext=decision.additional_context)

    return {}  # silence


def _post_tool_use_out(decision: Decision, hook_name: str) -> dict[str, Any]:
    objects = decision.action in (DecisionAction.BLOCK, DecisionAction.CHALLENGE)
    if objects and hook_name in CLAUDE.post_tool_block_events:
        out: dict[str, Any] = {"decision": "block", "reason": decision.reason}
        if decision.additional_context:
            out.update(_spec_out(hook_name, additionalContext=decision.additional_context))
        return out
    context = decision.additional_context
    if objects and decision.reason:
        # PostToolUseFailure cannot block; carry the objection as context instead.
        context = f"{decision.reason}\n\n{context}" if context else decision.reason
    if context:
        return _spec_out(hook_name, additionalContext=context)
    return {}


def _context_only_out(decision: Decision, hook_name: str) -> dict[str, Any]:
    """UserPromptSubmit: inject the task spec + planning budget (SPEC §9, §13)."""
    if decision.action is DecisionAction.BLOCK:
        return {"decision": "block", "reason": decision.reason}
    if decision.additional_context:
        return _spec_out(hook_name, additionalContext=decision.additional_context)
    return {}


# Findings that mean "the completion gate would hold this turn open". On an ALLOW that
# observe mode did not produce, they mean rationing silenced the gate: it gave up.
_GATE_BLOCKING_MODES = frozenset({FailureMode.FALSE_COMPLETION, FailureMode.UNVERIFIED_CHANGE})
_SEVERITY_ORDER = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def gate_gave_up(decision: Decision) -> str | None:
    """The unresolved problem, when the completion gate stopped holding a turn open.

    The core passes a turn once its per-task cap is spent, or when a stop hook is already
    holding the turn — correctly, since a gate that never lets go is a loop — but it does
    so silently, so the developer is left believing an unverified turn was verified
    (G10). The core does not flag this yet, so it is recognised here: an ALLOW that
    observe mode did not produce (``would_have`` unset) still carrying a blocking-grade
    completion finding.
    """
    if decision.action is not DecisionAction.ALLOW or decision.would_have is not None:
        return None
    for finding in decision.findings:
        if finding.failure_mode in _GATE_BLOCKING_MODES and _SEVERITY_ORDER.index(
            finding.severity
        ) >= _SEVERITY_ORDER.index(Severity.MEDIUM):
            return finding.summary or finding.subject or "unverified changes"
    return None


def _stop_out(decision: Decision, hook_name: str) -> dict[str, Any]:
    """Completion Gate (SPEC §19). Blocking Stop forces the agent to keep working."""
    if decision.action in (DecisionAction.BLOCK, DecisionAction.CHALLENGE) and CLAUDE.stop_block:
        return {"decision": "block", "reason": decision.reason}
    unresolved = gate_gave_up(decision)
    if unresolved and CLAUDE.system_message:
        return {
            "systemMessage": (
                f"AgentGuard: this turn ended unverified — {unresolved}. The completion "
                "gate stopped holding it open; check the result before relying on it."
            )
        }
    if decision.additional_context:
        return _spec_out(hook_name, additionalContext=decision.additional_context)
    return {}


def _session_start_out(decision: Decision) -> dict[str, Any]:
    # `watchPaths` is wired in Phase 1, once there is an index whose freshness depends
    # on specific files (manifests, lockfiles, config).
    if decision.additional_context:
        return _spec_out("SessionStart", additionalContext=decision.additional_context)
    return {}
