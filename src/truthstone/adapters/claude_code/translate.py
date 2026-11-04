"""Claude Code ⇄ Truthstone translation (SPEC §23, §26).

    "Every adapter translates its native events into this common representation."

This module is the *only* place in the codebase that knows Claude Code's JSON shape, and
every decision about how a core ``Decision`` is *rendered* for Claude Code lives in one
object, :data:`CLAUDE`, so a host-capability profile can replace it wholesale.

A safety property worth stating explicitly
------------------------------------------
**Truthstone never emits ``permissionDecision: "allow"``.**

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

from truthstone.adapters import mcp
from truthstone.adapters.claude_code.protocol import (
    SESSION_MODE_EVENT,
    SESSION_MODE_FIELD,
    SESSION_MODES,
    session_mode_message,
)
from truthstone.core import hosts
from truthstone.core.enums import DecisionAction, EventType
from truthstone.core.events import AgentEvent
from truthstone.core.models import Decision

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


@dataclass(frozen=True, slots=True)
class ClaudeRendering(hosts.HostCapabilities):
    """Claude Code's capability profile plus its native decision words. The one place to
    change how each core intent is expressed to Claude Code.

    Derived from the core's ``hosts.CLAUDE_CODE`` (``docs/ADAPTER-CONTRACT.md``): the
    capability fields are that profile's, the core's ladder (``hosts.render``) decides
    what to say, and the fields below only spell it.
    """

    # PreToolUse ``permissionDecision`` per ladder kind. Never "allow" (Truthstone does
    # not grant permissions) and never "defer" (see the module docstring). A rewrite is
    # an ``ask`` too, carrying ``updatedInput``: the developer approves the narrowed input.
    deny: str = "deny"  # CHALLENGE / BLOCK: the reason goes back to Claude
    review: str = "ask"  # REQUEST_REVIEW, and MODIFY: the developer's own permission prompt
    # Events that accept ``decision: "block"`` after a tool ran. PostToolUseFailure does
    # not: it takes ``additionalContext`` only. (The ladder's post-tool rule says the same.)
    post_tool_block_events: tuple[str, ...] = ("PostToolUse",)

    @property
    def stop_block(self) -> bool:
        """Stop / SubagentStop ``decision: "block"`` keeps the turn going (Claude Code caps
        consecutive continuations at 8; Truthstone's own cap is lower)."""
        return self.stop_continue != "none"

    @property
    def system_message(self) -> bool:
        """The universal ``systemMessage`` field: shown to the developer, never to Claude."""
        return self.system_message_visible


CLAUDE = ClaudeRendering(**hosts.profile_fields(hosts.CLAUDE_CODE))

# Kept as a module constant: tests and callers assert against it.
MODIFY_PERMISSION = CLAUDE.review
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

# The events Truthstone asks to be installed for. Anything else is noise.
SUBSCRIBED_EVENTS: tuple[str, ...] = tuple(EVENT_MAP)

# A Bash or PowerShell failure's ``error`` starts with this line (hooks docs, 2.1.317).
_EXIT_LINE = re.compile(r"^\s*Exit code (-?\d+)\s*$")


# -- per-session modes (R10) ---------------------------------------------------------------
#
# ``TRUTHSTONE_DISABLE=1 claude`` and ``TRUTHSTONE_OBSERVE=1 claude`` are per-session
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

# Claude Code re-enters the conversation with a synthetic prompt when a background task
# finishes (captured live, 2.1.317: tests/fixtures/hook_payloads/
# UserPromptSubmit.task_notification.json).
_HOST_NOTIFICATIONS = ("<task-notification>",)


def is_host_notification(prompt: Any) -> bool:
    """Whether a UserPromptSubmit carries Claude Code's own message, not the developer's."""
    return isinstance(prompt, str) and prompt.lstrip().startswith(_HOST_NOTIFICATIONS)


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

    if event_type is EventType.USER_PROMPT and is_host_notification(payload.get("prompt")):
        # Not a request. Read as one, it opened a new task — so the completion gate
        # forgot the real task's unverified edits — and injected a planning budget for
        # an XML block, which Claude itself called out as not fitting. The turn belongs
        # to the task already running.
        return None

    if event_type is EventType.POST_TOOL_FAILURE:
        result: Any = failure_result(payload)
    else:
        result = payload.get("tool_response", payload.get("tool_output"))

    tool = payload.get("tool_name")
    return AgentEvent(
        event=event_type,
        agent=AGENT_NAME,
        workspace=payload.get("cwd") or ".",
        session_id=session_id,
        tool=tool,
        arguments=payload.get("tool_input") or {},
        tool_use_id=payload.get("tool_use_id"),
        result=result,
        prompt_text=payload.get("prompt") or payload.get("prompt_text"),
        last_assistant_message=payload.get("last_assistant_message"),
        pending_tasks=pending_tasks(payload),
        # MCP (H5): read-only only when known; an `mcp__` tool is unknown, never a read.
        host_hints=mcp.host_hints(AGENT_NAME, tool),
        raw=payload,
    )


_TASK_FIELDS = ("id", "type", "status", "command")


def pending_tasks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Stop's ``background_tasks`` -> the core's ``pending_tasks`` (G7).

    Captured live (``Stop.background_tasks.json``): ``{"id", "type": "shell", "status":
    "running", "description", "command"}``. Only the four canonical fields are kept, as
    strings; anything malformed is dropped rather than guessed at.
    """
    tasks = payload.get("background_tasks")
    if not isinstance(tasks, list):
        return []
    return [
        {key: task[key] for key in _TASK_FIELDS if isinstance(task.get(key), str)}
        for task in tasks[:64]
        if isinstance(task, dict)
    ]


# -- outbound ------------------------------------------------------------------------------


def _spec_out(hook_name: str, **fields: Any) -> dict[str, Any]:
    body = {"hookEventName": hook_name}
    body.update({k: v for k, v in fields.items() if v is not None})
    return {"hookSpecificOutput": body}


def from_decision(event: AgentEvent, decision: Decision, hook_name: str) -> dict[str, Any]:
    """Decision -> Claude Code hook output JSON.

    An empty dict means "Truthstone has no opinion", which is the desired outcome for
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


def _render(decision: Decision, hook_name: str) -> dict[str, Any]:
    """The core's ladder decides (``hosts.render``); this only spells it for Claude Code."""
    return _emit(hosts.render(decision, CLAUDE, EVENT_MAP[hook_name]), hook_name)


def _emit(rendering: hosts.Rendering, hook_name: str) -> dict[str, Any]:
    kind = rendering.kind
    if kind == "deny":
        # "deny" hands the reason back to Claude, which then re-reasons with its own
        # intelligence and proposes something else (SPEC §21). This *is* the loop.
        out = _spec_out(
            hook_name, permissionDecision=CLAUDE.deny, permissionDecisionReason=rendering.reason
        )
    elif kind == "ask":
        # "ask": the reason is shown to the developer in the permission prompt. In a
        # `-p` run where nobody can answer, Claude Code denies the call and Claude reads
        # the same reason in the tool result.
        out = _spec_out(
            hook_name, permissionDecision=CLAUDE.review, permissionDecisionReason=rendering.reason
        )
    elif kind == "rewrite_ask":
        # The rewrite always announces itself — silently changing what the agent asked
        # for is a trust hazard even when the change is an improvement — and it is never
        # approved on the developer's behalf: "ask" shows them the narrowed input.
        out = _spec_out(
            hook_name,
            permissionDecision=MODIFY_PERMISSION,
            permissionDecisionReason=rendering.reason,
            updatedInput=rendering.updated_arguments,
            additionalContext=rendering.context,
        )
    elif kind == "block":
        out = {"decision": "block", "reason": rendering.reason}
        if rendering.context:
            out.update(_spec_out(hook_name, additionalContext=rendering.context))
    elif kind == "context":
        out = _spec_out(hook_name, additionalContext=rendering.context)
    else:
        out = {}  # silence
    if rendering.system_message and CLAUDE.system_message:
        out["systemMessage"] = rendering.system_message
    return out


def _pre_tool_use_out(decision: Decision) -> dict[str, Any]:
    return _render(decision, "PreToolUse")


def _post_tool_use_out(decision: Decision, hook_name: str) -> dict[str, Any]:
    # PostToolUseFailure cannot block; the ladder carries an objection there as context.
    return _render(decision, hook_name)


def _context_only_out(decision: Decision, hook_name: str) -> dict[str, Any]:
    """UserPromptSubmit: inject the task spec + planning budget (SPEC §9, §13)."""
    return _render(decision, hook_name)


def gate_gave_up(decision: Decision) -> str | None:
    """The unresolved problem, when the completion gate stopped holding a turn open.

    The core passes a turn once its per-task cap is spent, or when a stop hook is already
    holding the turn — correctly, since a gate that never lets go is a loop — and says
    so on ``Decision.unverified_finish`` (G10), so the developer is not left believing an
    unverified turn was verified. It is the core's explicit flag, not an inference from
    findings: an honest hand-back carries findings too, and is no give-up. Never on a
    decision observe mode produced (``would_have`` set), nor on anything but an ALLOW.
    """
    if decision.action is not DecisionAction.ALLOW or decision.would_have is not None:
        return None
    return decision.unverified_finish or None


def _stop_out(decision: Decision, hook_name: str) -> dict[str, Any]:
    """Completion Gate (SPEC §19). Blocking Stop forces the agent to keep working."""
    if decision.action in (DecisionAction.BLOCK, DecisionAction.CHALLENGE) and CLAUDE.stop_block:
        return {"decision": "block", "reason": decision.reason}
    # Only the main agent's Stop ends the developer's turn; a subagent finishing is not
    # the task finishing, and the core never gates it (G9).
    unresolved = gate_gave_up(decision) if hook_name == "Stop" else None
    if unresolved and CLAUDE.system_message:
        return {
            "systemMessage": (
                f"Truthstone: this turn ended unverified — {unresolved}. The completion "
                "gate stopped holding it open; check the result before relying on it."
            )
        }
    if decision.additional_context:
        return _spec_out(hook_name, additionalContext=decision.additional_context)
    return {}


def _session_start_out(decision: Decision) -> dict[str, Any]:
    # `watchPaths` is wired in Phase 1, once there is an index whose freshness depends
    # on specific files (manifests, lockfiles, config).
    return _render(decision, "SessionStart")
