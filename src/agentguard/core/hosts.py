"""Host capability profiles and the rendering ladder (``IMPROVEMENTS.md`` H1, §4.4).

The core decides what AgentGuard *means*: a :class:`~agentguard.core.models.Decision`.
Hosts differ in what they can be *told*, and the differences fail open. Codex 0.166.0
answers an ``ask`` by marking the hook failed and running the tool; Claude Code ignores a
``defer`` in interactive sessions and drops the rewrite that came with it. A naive mapping
from Decision to host output therefore guards nothing on exactly the actions that matter.

So rendering happens in two steps:

1. :func:`render` — pure, host-neutral, and the only place that decides. Given a
   decision, a host's :class:`HostCapabilities` and the phase the host is in, it picks the
   strongest form of the decision that this host can actually carry, and returns a
   :class:`Rendering` of one of six kinds.
2. The adapter spells that kind in its host's JSON (``docs/ADAPTER-CONTRACT.md`` has the
   table). It makes no policy choice of its own.

The ladder (each rung is used only if the host can carry it):

==================================  ===================================================
decision                            rendering
==================================  ===================================================
REQUEST_REVIEW, sign-off required   ``ask`` where the host's ask really asks; else a
                                    ``deny`` whose reason starts "needs developer
                                    sign-off: ask the user to confirm, then re-run"
REQUEST_REVIEW, advisory            ``ask`` if native; else non-blocking ``context``
MODIFY                              ``rewrite_ask`` where the developer reviews the
                                    rewritten input; else a CHALLENGE that shows the
                                    guarded form for the agent to re-issue
CHALLENGE / BLOCK before a tool     ``deny``; else ``context``; else record-only
BLOCK / CHALLENGE at Stop           ``block`` if the host can continue the agent
ALLOW + additional context          ``context`` if this phase has a channel; else silent
==================================  ===================================================

Properties every rendering has (``tests/test_hosts.py`` checks them for every profile,
every action and every phase):

* there is no kind for ``defer`` or for a grant (``allow``/approve), so neither can be
  produced;
* ``deny``, ``ask``, ``block`` and ``rewrite_ask`` always carry a non-empty reason (an
  empty one fails open on Codex, and helps no agent anywhere);
* a sign-off review never degrades to a mere ``context`` on a host that can deny.

It also states what an adapter is (:class:`Adapter`, H4); ``adapters/registry.py`` maps
adapter names to implementations.

This module must stay host-neutral: no host's tool, argument or field names appear in
it (``tests/test_core_host_neutral.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any, Literal, Protocol, runtime_checkable

from agentguard.core.enums import ChallengeCategory, DecisionAction, EventType
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision

AskSupport = Literal["native", "fails_open", "none"]
RewriteSupport = Literal["with_user_approval", "with_auto_approve", "none"]
StopContinue = Literal["same_turn", "new_prompt", "none"]
RenderKind = Literal["silent", "deny", "ask", "context", "block", "rewrite_ask"]

ASK_SUPPORT: frozenset[str] = frozenset({"native", "fails_open", "none"})
REWRITE_SUPPORT: frozenset[str] = frozenset({"with_user_approval", "with_auto_approve", "none"})
STOP_CONTINUE: frozenset[str] = frozenset({"same_turn", "new_prompt", "none"})
KINDS: frozenset[str] = frozenset({"silent", "deny", "ask", "context", "block", "rewrite_ask"})
# Kinds that interrupt or redirect the agent, so they must say why.
REASONED_KINDS: frozenset[str] = frozenset({"deny", "ask", "block", "rewrite_ask"})

# The phases a decision can be rendered in are the core's own event types.
PHASES: tuple[EventType, ...] = tuple(EventType)

# -- wording shared by every host ---------------------------------------------------------

FALLBACK_REASON = "AgentGuard objected to this action."
SIGNOFF_LEAD = "needs developer sign-off: ask the user to confirm, then re-run."
SIGNOFF_PREFIX = SIGNOFF_LEAD + "\n\n"
SIGNOFF_NOTICE = "AgentGuard is holding this for your sign-off: {headline}"
RISKY_LEAD = "AgentGuard: this command is risky as written."
GUARDED_FORM = "If this is what you intend, re-issue it in this guarded form:\n\n    {command}\n"
REWRITE_FALLBACK = "AgentGuard narrowed this command. Check the narrowed form before approving it."
UNVERIFIED_NOTICE = (
    "AgentGuard: this turn ended unverified — {problem}. The completion gate stopped "
    "holding it open; check the result before relying on it."
)


# -- capability profiles ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HostCapabilities:
    """What one host can be told, verified against that host (never assumed from docs).

    ``context_channels`` holds the phases (``EventType`` values) in which extra context
    reaches the agent. The literals are validated, so a typo fails at import, not by
    silently rendering nothing.
    """

    name: str
    # A pre-tool deny stops the call and hands the reason to the agent.
    can_block_pre: bool
    # Whether "ask the developer" really asks ("native"), is accepted but ignored so the
    # tool runs anyway ("fails_open"), or does not exist ("none").
    ask: AskSupport
    # How rewritten tool input is applied: shown to the developer for approval, applied
    # automatically, or not at all.
    rewrite: RewriteSupport
    # Whether an "allow" bypasses the host's own permission checks. AgentGuard never grants
    # either way; this says how dangerous a mistaken allow would be.
    allow_is_grant: bool
    context_channels: frozenset[str]
    # What a Stop block does: continue the same turn, continue through a new prompt that
    # carries the reason, or nothing.
    stop_continue: StopContinue
    # Whether a developer-facing message reaches a person.
    system_message_visible: bool
    # Whether a failed tool call arrives as its own failure event.
    failure_event: bool
    # Whether a shell result tells the core the command's exit code.
    exit_code_in_result: bool
    # The host's own limit on consecutive Stop continuations; None when it has none or it
    # is unknown. The core's per-task cap applies regardless.
    host_continuation_cap: int | None

    def __post_init__(self) -> None:
        if self.ask not in ASK_SUPPORT:
            raise ValueError(f"{self.name}: unknown ask support {self.ask!r}")
        if self.rewrite not in REWRITE_SUPPORT:
            raise ValueError(f"{self.name}: unknown rewrite support {self.rewrite!r}")
        if self.stop_continue not in STOP_CONTINUE:
            raise ValueError(f"{self.name}: unknown stop behaviour {self.stop_continue!r}")
        channels = frozenset(EventType(channel).value for channel in self.context_channels)
        object.__setattr__(self, "context_channels", channels)

    def can_say(self, phase: EventType | str) -> bool:
        """Whether this phase has a context channel."""
        return str(phase) in self.context_channels


def profile_fields(caps: HostCapabilities) -> dict[str, Any]:
    """The capability fields of a profile, for building a host-specific subclass of it."""
    return {field.name: getattr(caps, field.name) for field in fields(HostCapabilities)}


CLAUDE_CODE = HostCapabilities(
    name="claude-code",
    # A pre-tool "deny" blocks the call; Claude reads the reason and re-plans.
    can_block_pre=True,
    # "ask" opens the developer's own permission prompt. In `claude -p` nobody can answer
    # and the call is denied with the same reason, which still holds the action.
    ask="native",
    # "ask" together with rewritten input shows the developer the modified input, and the
    # call runs only if they approve it (live-verified, docs/CLAUDE-PLUGIN.md).
    rewrite="with_user_approval",
    # "allow" skips the developer's permission prompt: a grant. Never sent.
    allow_is_grant=True,
    # Extra context reaches Claude at session start, on the prompt, before and after a
    # tool, and after a failed tool (the failure event accepts nothing else). Stop does
    # not take it.
    context_channels=frozenset(
        {
            EventType.SESSION_START,
            EventType.USER_PROMPT,
            EventType.PRE_TOOL_USE,
            EventType.POST_TOOL_USE,
            EventType.POST_TOOL_FAILURE,
        }
    ),
    # A Stop block keeps the same turn going; the next Stop is marked as a continuation.
    stop_continue="same_turn",
    # The developer sees the system message (live: "Stop says: …").
    system_message_visible=True,
    # A non-zero shell exit arrives as a separate failure event whose text starts with
    # "Exit code N", so the exit code is known for failures.
    failure_event=True,
    exit_code_in_result=True,
    # Claude Code stops honouring Stop blocks after 8 consecutive continuations.
    host_continuation_cap=8,
)

CODEX = HostCapabilities(
    name="codex",
    # A pre-tool deny with a non-empty reason blocks the call (live, codex-cli 0.166.0).
    can_block_pre=True,
    # The binary says "PreToolUse hook returned unsupported permissionDecision:ask": the
    # hook is marked failed and the tool RUNS. An ask would hold nothing.
    ask="fails_open",
    # "allow" with rewritten input rewrites the call, and Codex's approval policy and
    # sandbox still apply afterwards; nobody reviews the rewrite itself.
    rewrite="with_auto_approve",
    # Not a grant: approval policy and sandbox still run after the hook (live).
    allow_is_grant=False,
    # Context is accepted on these four; on Stop it invalidates the whole output.
    context_channels=frozenset(
        {
            EventType.SESSION_START,
            EventType.USER_PROMPT,
            EventType.PRE_TOOL_USE,
            EventType.POST_TOOL_USE,
        }
    ),
    # A Stop block continues: the reason becomes a new continuation prompt. No prompt
    # hook fires for that continuation in 0.166.0, so the task simply carries on.
    stop_continue="new_prompt",
    # Shown in the TUI and the desktop app; `codex exec` never displays it, so nothing
    # that matters may depend on it alone.
    system_message_visible=True,
    # Non-zero exits arrive through the ordinary post-tool event.
    failure_event=False,
    # The shell result is plain output text, with no exit code.
    exit_code_in_result=False,
    host_continuation_cap=None,
)

CONSERVATIVE = HostCapabilities(
    name="conservative",
    # Deny is the one decision every hook-capable host implements; assumed to work.
    can_block_pre=True,
    # An unverified ask may be ignored (Codex, Cursor's preToolUse): never relied upon,
    # so a sign-off becomes a deny.
    ask="fails_open",
    # An unverified rewrite may be dropped, or applied without anyone seeing it.
    rewrite="none",
    # Assume the worst of an allow.
    allow_is_grant=True,
    # An unknown field can invalidate a host's whole output (Codex does exactly that),
    # taking a deny down with it. Say nothing that is not essential.
    context_channels=frozenset(),
    # A Stop block is assumed to hold the turn. No claim is made about a later prompt,
    # so nothing expects one.
    stop_continue="same_turn",
    # Nobody may be watching.
    system_message_visible=False,
    failure_event=False,
    exit_code_in_result=False,
    host_continuation_cap=None,
)

_PROFILES: dict[str, HostCapabilities] = {caps.name: caps for caps in (CLAUDE_CODE, CODEX)}


def register_profile(caps: HostCapabilities) -> None:
    """Make a new host's profile known to :func:`capabilities_for` (adapter import time)."""
    _PROFILES[caps.name] = caps


def capabilities_for(agent: str | None) -> HostCapabilities:
    """The profile for an ``AgentEvent.agent`` value. Unknown hosts get CONSERVATIVE."""
    key = (agent or "").strip().lower().replace("_", "-")
    return _PROFILES.get(key, CONSERVATIVE)


# -- the adapter protocol (H4) ---------------------------------------------------------------


@runtime_checkable
class Adapter(Protocol):
    """What the daemon needs from a host adapter (``docs/ADAPTER-CONTRACT.md``, (d)).

    * ``name`` — the route, ``POST /hook/<name>``, and normally ``AgentEvent.agent``;
    * ``to_event(payload)`` — the host's hook payload as a core event, or ``None`` for a
      payload the core should not see;
    * ``from_decision(event, decision, hook_name)`` — the hook's output; ``{}`` means "no
      opinion". It spells ``render(decision, profile, phase)`` and decides nothing itself;
    * ``handle_payload`` — optional, ``None`` when absent. For hosts whose one payload
      stands for several actions: it calls ``guard.handle`` per action, combines the
      answers, and replaces the three-step path.

    Every method fails open: a payload it cannot read is "no opinion", never an error.
    """

    name: str
    handle_payload: Callable[[Any, dict[str, Any]], dict[str, Any]] | None

    def to_event(self, payload: dict[str, Any]) -> AgentEvent | None: ...

    def from_decision(self, event: AgentEvent, decision: Decision, hook_name: str) -> dict[str, Any]: ...


# -- the ladder ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rendering:
    """What to say to the host, before it is spelled in the host's JSON.

    * ``kind`` is what reaches the agent or the host's permission flow;
    * ``reason`` is the text of a deny, ask, block or rewrite_ask (never empty for those);
    * ``updated_arguments`` is the rewritten tool input (``rewrite_ask`` only);
    * ``context`` is non-blocking extra context for the agent;
    * ``system_message`` is for the developer, never the agent, and can accompany any kind;
    * ``expects_continuation`` marks a Stop block whose continuation arrives as a new
      prompt, which belongs to the current task rather than opening a new one.
    """

    kind: RenderKind
    reason: str = ""
    updated_arguments: dict[str, Any] | None = None
    context: str | None = None
    system_message: str | None = None
    expects_continuation: bool = False

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown rendering kind {self.kind!r}")
        if self.kind in REASONED_KINDS and not self.reason.strip():
            raise ValueError(f"a {self.kind} must carry a reason")
        if (self.kind == "rewrite_ask") != (self.updated_arguments is not None):
            raise ValueError("rewritten arguments travel with rewrite_ask, and only with it")
        if self.kind == "context" and not (self.context or "").strip():
            raise ValueError("a context rendering must carry context")

    @property
    def is_silent(self) -> bool:
        """Nothing reaches anyone: no agent-facing kind and no developer notice."""
        return self.kind == "silent" and not self.system_message


SILENT = Rendering("silent")


def render(decision: Decision, caps: HostCapabilities, phase: EventType | str) -> Rendering:
    """The strongest form of ``decision`` that this host can carry in this phase. Pure."""
    try:
        phase = EventType(phase)
    except ValueError:
        return SILENT
    if phase is EventType.PRE_TOOL_USE:
        return _pre_tool(decision, caps)
    if phase in (EventType.POST_TOOL_USE, EventType.POST_TOOL_FAILURE):
        return _post_tool(decision, caps, phase)
    if phase in (EventType.STOP, EventType.SUBAGENT_STOP):
        return _stop(decision, caps, phase)
    if phase is EventType.USER_PROMPT:
        return _prompt(decision, caps)
    if phase is EventType.SESSION_START:
        # Nothing has happened yet, so there is nothing to ask about, deny or hold.
        return _context_or_silent(caps, phase, decision.additional_context)
    return SILENT  # session end: no host acts on an answer


def _pre_tool(decision: Decision, caps: HostCapabilities) -> Rendering:
    phase = EventType.PRE_TOOL_USE
    action = decision.action
    if action in (DecisionAction.CHALLENGE, DecisionAction.BLOCK):
        return _objection(caps, _reason(decision))
    if action is DecisionAction.REQUEST_REVIEW:
        if caps.ask == "native":
            return Rendering("ask", reason=_reason(decision))
        if decision.signoff_required:
            # The developer must say yes, and this host's ask would not ask: refuse, and
            # say who has to agree. The agent asks the user, then re-runs.
            notice = None
            if caps.system_message_visible:
                notice = SIGNOFF_NOTICE.format(headline=_headline(decision)[:200])
            return _objection(caps, SIGNOFF_PREFIX + _reason(decision).strip(), notice)
        return _context_or_silent(caps, phase, _unsayable(decision))
    if action is DecisionAction.MODIFY:
        arguments = decision.updated_arguments
        if arguments and caps.rewrite == "with_user_approval" and caps.ask == "native":
            # The developer sees the narrowed input in their own prompt and approves it.
            announcement = _text(decision.additional_context) or _text(decision.reason)
            return Rendering(
                "rewrite_ask",
                reason=announcement or REWRITE_FALLBACK,
                updated_arguments=dict(arguments),
                context=announcement,
            )
        # Nobody would review a rewrite here: challenge, and hand back the guarded form.
        return _objection(caps, _guarded_form(decision))
    return _context_or_silent(caps, phase, decision.additional_context)


def _post_tool(decision: Decision, caps: HostCapabilities, phase: EventType) -> Rendering:
    objects = decision.action in (DecisionAction.CHALLENGE, DecisionAction.BLOCK)
    if objects and phase is EventType.POST_TOOL_USE:
        context = _text(decision.additional_context) if caps.can_say(phase) else None
        return Rendering("block", reason=_reason(decision), context=context)
    # A failure event cannot block (the tool already failed), and nothing can be asked
    # after the fact: what is left is context.
    return _context_or_silent(caps, phase, _unsayable(decision))


def _stop(decision: Decision, caps: HostCapabilities, phase: EventType) -> Rendering:
    notice = None
    unverified = _text(getattr(decision, "unverified_finish", None))
    if unverified and caps.system_message_visible:
        notice = UNVERIFIED_NOTICE.format(problem=unverified.strip().rstrip("."))
    if decision.action in (DecisionAction.BLOCK, DecisionAction.CHALLENGE):
        if caps.stop_continue != "none":
            return Rendering(
                "block",
                reason=_reason(decision),
                expects_continuation=caps.stop_continue == "new_prompt",
            )
        # The host cannot keep the agent working. Never silently: tell the developer.
        if caps.system_message_visible and notice is None:
            notice = UNVERIFIED_NOTICE.format(problem=_problem(decision))
    return _context_or_silent(caps, phase, _unsayable(decision), notice)


def _prompt(decision: Decision, caps: HostCapabilities) -> Rendering:
    phase = EventType.USER_PROMPT
    if decision.action is DecisionAction.BLOCK:
        return Rendering("block", reason=_reason(decision))
    if decision.action is DecisionAction.CHALLENGE:
        # A challenge is a question about an action, and a prompt is not one. It is never
        # a refusal of the developer's prompt; only its context is passed on.
        return _context_or_silent(caps, phase, decision.additional_context)
    return _context_or_silent(caps, phase, _unsayable(decision))


def _unsayable(decision: Decision) -> str | None:
    """The text left when a decision cannot be asked, denied or blocked in this phase.

    * an objection (CHALLENGE / BLOCK) about a tool action: its reason, then any context;
    * a review: the review itself (its reason), as non-blocking context;
    * anything else (ALLOW, and a MODIFY that can no longer apply): the context alone.
    """
    if decision.action in (DecisionAction.CHALLENGE, DecisionAction.BLOCK):
        return _merge(decision.reason, decision.additional_context)
    if decision.action is DecisionAction.REQUEST_REVIEW:
        return decision.reason
    return decision.additional_context


def _objection(caps: HostCapabilities, text: str, notice: str | None = None) -> Rendering:
    """CHALLENGE before a tool: deny, else context, else record-only."""
    if caps.can_block_pre:
        return Rendering("deny", reason=text, system_message=notice)
    # A host that cannot stop the call can still be told, on either side of it. When only
    # the post-tool side has a channel, the adapter delivers it with the tool's result.
    if caps.can_say(EventType.PRE_TOOL_USE) or caps.can_say(EventType.POST_TOOL_USE):
        return Rendering("context", context=text, system_message=notice)
    return Rendering("silent", system_message=notice)


def _context_or_silent(
    caps: HostCapabilities, phase: EventType, text: str | None, notice: str | None = None
) -> Rendering:
    text = _text(text)
    if text and caps.can_say(phase):
        return Rendering("context", context=text, system_message=notice)
    return Rendering("silent", system_message=notice)


# -- text -----------------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    """The value itself if it has any content; blank text counts as absent."""
    return value if isinstance(value, str) and value.strip() else None


def _reason(decision: Decision) -> str:
    return _text(decision.reason) or FALLBACK_REASON


def _merge(*parts: str | None) -> str | None:
    kept = [part for part in parts if _text(part)]
    return "\n\n".join(kept) if kept else None


def _headline(decision: Decision) -> str:
    """One line a developer can act on: the risk finding's own summary when there is one."""
    for finding in decision.findings:
        if finding.category is ChallengeCategory.RISK and finding.summary.strip():
            return finding.summary.strip()
    return _first_line(_reason(decision))


def _problem(decision: Decision) -> str:
    for finding in decision.findings:
        if finding.summary.strip():
            return finding.summary.strip().rstrip(".")
    return _first_line(_reason(decision)).rstrip(".")


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), FALLBACK_REASON)


def _guarded_form(decision: Decision) -> str:
    """MODIFY as a challenge: what is wrong, and the form to re-issue if it is intended.

    The finding's own explanation is used rather than the core's "narrowed this command"
    summary, which would be untrue here: nothing was narrowed, the agent decides.
    """
    detail = next((f.detail.strip() for f in decision.findings if f.detail and f.detail.strip()), "")
    why = detail.split(". ")[0].rstrip(".") + "." if detail else _reason(decision).strip()
    parts = [f"{RISKY_LEAD} {why}"]
    command = (decision.updated_arguments or {}).get("command")
    if isinstance(command, str) and command.strip():
        parts.append(GUARDED_FORM.format(command=command))
    return "\n\n".join(parts)
