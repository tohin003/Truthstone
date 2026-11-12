"""Every decision about what Truthstone *says* to Codex, in one place.

The core decides *what* to do; the core's rendering ladder (``core/hosts.py``, H1) decides
the strongest form of it that Codex can carry; this module only spells that form in
Codex's hook JSON. Nothing else in the adapter makes a rendering choice.

The Codex profile is ``hosts.CODEX``, verified against ``codex-rs`` and live runs
(``docs/CODEX.md``):

=============================  =========================================================
capability                     Codex 0.166.0
=============================  =========================================================
``ask``                        unsupported — the hook is marked failed and the tool RUNS
``defer``                      rejected by the output schema — fails open the same way
``allow`` + ``updatedInput``   rewrites the call; Codex's approval policy and sandbox
                               still apply afterwards, so it is not a grant
Stop ``decision: block``       continues the turn; the reason becomes the next prompt
``additionalContext``          supported on SessionStart, UserPromptSubmit, Pre/PostToolUse
``systemMessage``              shown in the TUI/app; ``codex exec`` does not display it
=============================  =========================================================

What the ladder makes of that (flagged for the user in ``docs/CODEX.md``):

* **REQUEST_REVIEW** that needs the developer's sign-off is a ``deny`` whose reason starts
  "needs developer sign-off: ask the user to confirm, then re-run". An advisory review
  is passed on as non-blocking context, or only recorded. Codex has no ``ask``, and an
  ``ask`` that fails open would be worse than either.
* **MODIFY** is a ``deny`` that shows the guarded form for the agent to re-issue. The
  core's automatic rewrites were found unsound (``IMPROVEMENTS.md`` A5: ``rm -rf $HOME``
  still deletes home once "guarded"), so rewriting through ``allow`` + ``updatedInput`` is
  off. ``ENABLE_REWRITES`` is the one switch that turns it back on; it is the only path
  that bypasses the ladder, and it is never a grant on Codex.
"""

from __future__ import annotations

from typing import Any

from truthstone.core import hosts
from truthstone.core.enums import ChallengeCategory, DecisionAction, EventType, Severity, Verdict
from truthstone.core.events import AgentEvent
from truthstone.core.models import Decision

SHELL_TOOL = "Bash"
FALLBACK_REASON = hosts.FALLBACK_REASON
SIGN_OFF = hosts.SIGNOFF_PREFIX
GUARDED_FORM = hosts.GUARDED_FORM

# Replaced by the core's profile (H1). Both names stay importable.
CodexCapabilities = hosts.HostCapabilities
CODEX_0_166 = hosts.CODEX

# The single switch for MODIFY-as-rewrite. Off in this release (see the module docstring);
# when off, MODIFY is rendered as a challenge carrying the guarded form instead.
ENABLE_REWRITES = False

# The one closing line of every deny and hold the agent reads (day 5, T5). Before it, the agent
# answered every first intervention by opening the plugin's skill to learn how to respond: one
# extra model request (the whole session re-sent) per guarded cell that heard the guard. The
# skill's guidance an agent needs at that moment is this line; the rest is already in each
# message (its evidence, what to do, the accepted finishes). Never on a silent or allowing
# answer, and never on a context note.
CLOSING = (
    "This message is complete: do what it asks, without working around it, then report the actual result."
)
# Where a deny or block is read by the agent. A blocked prompt is the developer's to read.
_CLOSED_HOOKS = frozenset({"PreToolUse", "PostToolUse", "Stop", "SubagentStop"})

# Codex hook name -> the phase the ladder renders for. Kept here rather than imported from
# ``translate`` (which imports this module).
_PHASES: dict[str, EventType] = {
    "SessionStart": EventType.SESSION_START,
    "UserPromptSubmit": EventType.USER_PROMPT,
    "PreToolUse": EventType.PRE_TOOL_USE,
    "PostToolUse": EventType.POST_TOOL_USE,
    "Stop": EventType.STOP,
    "SubagentStop": EventType.SUBAGENT_STOP,
    "SessionEnd": EventType.SESSION_END,
}
_CONTEXT_HOOKS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse")


def _spec_out(hook_name: str, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"hookEventName": hook_name}
    body.update({k: v for k, v in fields.items() if v is not None})
    return {"hookSpecificOutput": body}


def _deny(reason: str) -> dict[str, Any]:
    # Codex rejects a deny with an empty reason (and then runs the tool), so never send one.
    return _spec_out(
        "PreToolUse",
        permissionDecision="deny",
        permissionDecisionReason=reason.strip() or FALLBACK_REASON,
    )


def is_irreversible(decision: Decision) -> bool:
    """A review request about an action that cannot be taken back.

    The core says so explicitly with ``Decision.signoff_required``. This is the fallback
    for a decision that lost the flag on the way (one built by hand, or merged from
    several): a RISK finding that requires a human, or any RISK finding of high or
    critical severity. Erring here means asking the developer once too often, never
    letting an irreversible action through unasked.
    """
    return any(
        finding.category is ChallengeCategory.RISK
        and (
            finding.verdict is Verdict.REQUIRES_HUMAN
            or finding.severity in (Severity.HIGH, Severity.CRITICAL)
        )
        for finding in decision.findings
    )


def render(
    event: AgentEvent,
    decision: Decision,
    hook_name: str,
    caps: hosts.HostCapabilities = CODEX_0_166,
    rewrites: bool | None = None,
) -> dict[str, Any]:
    """Decision -> Codex hook stdout. ``{}`` means "no opinion": print nothing."""
    phase = _PHASES.get(hook_name)
    if phase is None:
        return {}
    rewrites = ENABLE_REWRITES if rewrites is None else rewrites

    if decision.action is DecisionAction.MODIFY and phase is EventType.PRE_TOOL_USE:
        command = (decision.updated_arguments or {}).get("command")
        usable = event.tool == SHELL_TOOL and isinstance(command, str) and bool(command.strip())
        if usable and rewrites and caps.rewrite == "with_auto_approve" and not caps.allow_is_grant:
            # Off by default. When on: Codex's only rewrite form, announced to the agent.
            return _spec_out(
                "PreToolUse",
                permissionDecision="allow",
                updatedInput={"command": command},
                additionalContext=decision.additional_context or decision.reason or None,
            )
        if not usable:
            # A guarded form only means something for a shell command.
            decision = decision.model_copy(update={"updated_arguments": None})

    if (
        decision.action is DecisionAction.REQUEST_REVIEW
        and not decision.signoff_required
        and is_irreversible(decision)
    ):
        decision = decision.model_copy(update={"signoff_required": True})

    return _emit(hosts.render(decision, caps, phase), hook_name)


def _emit(rendering: hosts.Rendering, hook_name: str) -> dict[str, Any]:
    """A ladder rendering, spelled in Codex's hook JSON."""
    kind = rendering.kind
    if kind == "ask":
        # Only reachable with a profile whose ask is native; no Codex release has one.
        out = _spec_out(
            "PreToolUse", permissionDecision="ask", permissionDecisionReason=rendering.reason.strip()
        )
    elif kind in ("deny", "rewrite_ask"):
        # Codex cannot show anyone a rewrite (``updatedInput`` needs ``allow``): refuse.
        out = _deny(_closed(rendering.reason, hook_name))
    elif kind == "block":
        # Stop's output takes no ``hookSpecificOutput`` at all; the ladder only attaches
        # context to a post-tool block.
        out = {"decision": "block", "reason": _closed(rendering.reason, hook_name)}
        if rendering.context:
            out.update(_spec_out(hook_name, additionalContext=rendering.context))
    elif kind == "context":
        out = _context(rendering.context, hook_name)
    else:
        out = {}
    if rendering.system_message:
        # Shown in the TUI/app (not by `codex exec`): the developer is the one told.
        out["systemMessage"] = rendering.system_message
    return out


def _closed(reason: str, hook_name: str) -> str:
    """A deny's or block's reason, ending in :data:`CLOSING` (once) where the agent reads it."""
    reason = reason.strip() or FALLBACK_REASON
    if hook_name not in _CLOSED_HOOKS or reason.endswith(CLOSING):
        return reason
    return f"{reason}\n\n{CLOSING}"


def perceived(output: dict[str, Any]) -> str | None:
    """What the agent perceives of a hook output: ``deny``, ``ask``, ``block``, ``context``,
    or None (nothing, or only a ``systemMessage``, which is the developer's). Claude Code's
    hook output spells these the same way. Offline replay counts interventions with it."""
    if not output:
        return None
    if output.get("decision") == "block":
        return "block"
    specific = output.get("hookSpecificOutput") or {}
    permission = specific.get("permissionDecision")
    if permission in ("deny", "ask"):
        return str(permission)
    if specific.get("additionalContext"):
        return "context"
    return None


def _context(text: str | None, hook_name: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text or hook_name not in _CONTEXT_HOOKS:
        return {}
    return _spec_out(hook_name, additionalContext=text)
