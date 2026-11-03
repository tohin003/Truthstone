"""Every decision about what AgentGuard *says* to Codex, in one place.

This module is the plug-in point for the core's planned ``HostCapabilities`` profile
(``IMPROVEMENTS.md`` H1, §4.4): the core decides *what* to do; this module decides how that
can be expressed to Codex 0.166.0 without failing open. Nothing else in the adapter makes a
rendering choice.

The Codex profile, verified against ``codex-rs`` and live runs (``docs/CODEX.md``):

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

Policy decisions taken on that basis (flagged for the user in ``docs/CODEX.md``):

* **REQUEST_REVIEW** for an irreversible or destructive action is a ``deny`` whose reason
  asks for the developer's sign-off. A review request about anything else is passed on as
  non-blocking context, or only recorded. Codex has no ``ask``, and an ``ask`` that fails
  open would be worse than either.
* **MODIFY** is a ``deny`` that shows the guarded form for the agent to re-issue. The
  core's automatic rewrites were found unsound (``IMPROVEMENTS.md`` A5: ``rm -rf $HOME``
  still deletes home once "guarded"), so rewriting through ``allow`` + ``updatedInput`` is
  off. ``ENABLE_REWRITES`` is the one switch that turns it back on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentguard.core.enums import ChallengeCategory, DecisionAction, Severity, Verdict
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision

SHELL_TOOL = "Bash"
FALLBACK_REASON = "AgentGuard objected to this action."
SIGN_OFF = (
    "AgentGuard: needs developer sign-off. Ask the user to confirm, then re-run.\n\n"
)
GUARDED_FORM = "If this is what you intend, re-issue it in this guarded form:\n\n    {command}\n"


@dataclass(frozen=True, slots=True)
class CodexCapabilities:
    """What Codex can be told. The core's HostCapabilities profile will replace this."""

    ask: bool = False
    defer: bool = False
    rewrite_via_allow: bool = True  # allow + updatedInput rewrites; it is not a grant
    stop_block_continues: bool = True
    additional_context: bool = True
    system_message_in_exec: bool = False


CODEX_0_166 = CodexCapabilities()

# The single switch for MODIFY-as-rewrite. Off in this release (see the module docstring);
# when off, MODIFY is rendered as a challenge carrying the guarded form instead.
ENABLE_REWRITES = False


def _spec_out(hook_name: str, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"hookEventName": hook_name}
    body.update({k: v for k, v in fields.items() if v is not None})
    return {"hookSpecificOutput": body}


def _reason(decision: Decision) -> str:
    return (decision.reason or "").strip() or FALLBACK_REASON


def _deny(reason: str) -> dict[str, Any]:
    # Codex rejects a deny with an empty reason (and then runs the tool), so never send one.
    return _spec_out(
        "PreToolUse",
        permissionDecision="deny",
        permissionDecisionReason=reason.strip() or FALLBACK_REASON,
    )


def is_irreversible(decision: Decision) -> bool:
    """A review request about an action that cannot be taken back.

    Today the only producer is the risky-command check (force push, hard reset, recursive
    deletes, destructive SQL, ...): a RISK finding that requires a human, or any RISK finding
    of high or critical severity.
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
    caps: CodexCapabilities = CODEX_0_166,
    rewrites: bool | None = None,
) -> dict[str, Any]:
    """Decision -> Codex hook stdout. ``{}`` means "no opinion": print nothing."""
    rewrites = ENABLE_REWRITES if rewrites is None else rewrites
    action = decision.action

    if hook_name == "PreToolUse":
        if action in (DecisionAction.CHALLENGE, DecisionAction.BLOCK):
            return _deny(_reason(decision))
        if action is DecisionAction.REQUEST_REVIEW:
            if caps.ask:  # pragma: no cover - no Codex release supports it yet
                return _spec_out(
                    "PreToolUse", permissionDecision="ask", permissionDecisionReason=_reason(decision)
                )
            if is_irreversible(decision):
                out = _deny(SIGN_OFF + _reason(decision))
                # Shown in the TUI/app (not by `codex exec`): the developer is the one asked.
                out["systemMessage"] = (
                    f"AgentGuard is holding this for your sign-off: {_headline(decision)[:200]}"
                )
                return out
            return _context(decision.reason, hook_name)
        if action is DecisionAction.MODIFY:
            return _modify(event, decision, caps, rewrites)
        return _context(decision.additional_context, hook_name)

    if hook_name == "PostToolUse":
        if action in (DecisionAction.CHALLENGE, DecisionAction.BLOCK):
            out: dict[str, Any] = {"decision": "block", "reason": _reason(decision)}
            if decision.additional_context:
                out.update(_spec_out(hook_name, additionalContext=decision.additional_context))
            return out
        if action is DecisionAction.REQUEST_REVIEW:
            return _context(decision.reason, hook_name)
        return _context(decision.additional_context, hook_name)

    if hook_name == "UserPromptSubmit":
        if action is DecisionAction.BLOCK:
            return {"decision": "block", "reason": _reason(decision)}
        if action is DecisionAction.REQUEST_REVIEW:
            return _context(decision.reason, hook_name)
        return _context(decision.additional_context, hook_name)

    if hook_name in ("Stop", "SubagentStop"):
        # The completion gate. Codex's Stop output has no hookSpecificOutput at all, and any
        # unknown field invalidates it, so only decision/reason is ever sent.
        if action in (DecisionAction.BLOCK, DecisionAction.CHALLENGE) and caps.stop_block_continues:
            return {"decision": "block", "reason": _reason(decision)}
        return {}  # REQUEST_REVIEW at Stop: recorded only

    if hook_name == "SessionStart":
        return _context(decision.additional_context, hook_name)

    return {}  # SessionEnd and anything else: output is ignored by Codex


def _headline(decision: Decision) -> str:
    """One line a developer can act on: the risk finding's own summary when there is one."""
    for finding in decision.findings:
        if finding.category is ChallengeCategory.RISK and finding.summary.strip():
            return finding.summary.strip()
    return next(line.strip() for line in (_reason(decision) + "\n").splitlines() if line.strip())


def _context(text: str | None, hook_name: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text or hook_name not in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"):
        return {}
    return _spec_out(hook_name, additionalContext=text)


def _modify(event: AgentEvent, decision: Decision, caps: CodexCapabilities, rewrites: bool) -> dict[str, Any]:
    updated = decision.updated_arguments or {}
    command = updated.get("command")
    usable = event.tool == SHELL_TOOL and isinstance(command, str) and bool(command.strip())
    if usable and rewrites and caps.rewrite_via_allow:
        # Off by default. When on: Codex's only rewrite form, announced to the agent.
        return _spec_out(
            "PreToolUse",
            permissionDecision="allow",
            updatedInput={"command": command},
            additionalContext=decision.additional_context or decision.reason or None,
        )
    # A challenge instead: say what is wrong (the finding's own explanation, not the core's
    # "narrowed this command" summary, which would be untrue here) and hand back the form
    # to re-issue. Re-issuing it is the agent's decision, made with the evidence in view.
    detail = next((f.detail.strip() for f in decision.findings if f.detail and f.detail.strip()), "")
    why = detail.split(". ")[0].rstrip(".") + "." if detail else _reason(decision)
    parts = [f"AgentGuard: this command is risky as written. {why}"]
    if usable:
        parts.append(GUARDED_FORM.format(command=command))
    return _deny("\n\n".join(parts))
