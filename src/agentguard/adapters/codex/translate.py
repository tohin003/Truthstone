"""Codex ⇄ AgentGuard translation.

This module is the only place in the codebase that knows Codex's hook JSON. Every field
name below was read off payloads captured from a live ``codex exec`` (codex-cli 0.166.0,
``tests/fixtures/codex_payloads/``) and checked against ``codex-rs/hooks`` at
``rust-v0.166.0``; ``docs/CODEX.md`` has the full contract table. What gets *said* back to
Codex is decided in one place, ``render.py``.

Vocabulary
----------
The core speaks Claude Code's tool names. Codex has two tools that matter, and they map
like this:

* ``Bash`` (``exec_command`` and the shell tools; Codex already calls them ``Bash`` in
  hooks) → ``Bash`` with a single ``command`` string. Older Codex shell tools sent an
  argv list; ``[sh, -c, script]`` becomes ``script`` and anything else is
  ``shlex.join``-ed, so the core's command checks always see one string.
* ``apply_patch`` → one core event **per file** in the patch:

  ===================  =====================================================
  patch operation      core event
  ===================  =====================================================
  ``Add File``         ``Write`` {file_path, content}
  ``Update File``      ``Edit`` (one region) or ``MultiEdit`` (several), with
                       old/new strings that reproduce Codex's result exactly
  ``Delete File``      ``Delete`` {file_path} — mutating, so it is validated
                       and recorded as a changed file
  ``Update`` + ``Move``  ``Write`` at the destination + ``Delete`` of the source
  ===================  =====================================================

  A multi-file patch is evaluated file by file and the **strictest decision wins**
  (BLOCK > CHALLENGE > REQUEST_REVIEW > MODIFY > ALLOW); every objection's reason is
  passed back, labelled with its file, so the agent can fix all of them in one retry.

Reads are not writes
--------------------
Codex has no separate read tools: ``cat``, ``rg``, ``ls`` and ``git status`` all arrive as
``Bash``, and every one of them goes to the core, exactly as Claude Code's Bash calls do.
The core has the one shell classifier (``validate.shell`` + ``validate.checks.read_only``):
after its Level-0 checks (risk, self-protection, verification bypass), a command that only
reads or only runs the tests skips evidence and scope (``IMPROVEMENTS.md`` A4). This
adapter used to keep a second classifier and drop "read-only" commands before the core saw
them, which skipped the Level-0 checks too — and the two classifiers disagreed: it read
``cat f;rm -rf /`` as a read, since ``shlex`` does not split a ``;`` glued to a word.

Unknown tools (MCP tools, ``update_plan``, ...) are never validated as writes either: their
PreToolUse is ignored, their PostToolUse is recorded under the tool's own name with the
arguments namespaced under ``input``, so no ``file_path`` they carry is taken for an edit.
The installer does not subscribe to them in the first place.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from agentguard.adapters.codex import patch as patchlib
from agentguard.adapters.codex import render as rendering
from agentguard.core.enums import DecisionAction, EventType
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision
from agentguard.repo.paths import relative_path
from agentguard.validate import checks, shell

AGENT_NAME = "codex"

# Codex hook event name -> normalized event type. PermissionRequest is deliberately
# absent: answering it would mean granting or refusing permissions, and AgentGuard
# never grants them.
EVENT_MAP: dict[str, EventType] = {
    "SessionStart": EventType.SESSION_START,
    "UserPromptSubmit": EventType.USER_PROMPT,
    "PreToolUse": EventType.PRE_TOOL_USE,
    "PostToolUse": EventType.POST_TOOL_USE,
    "Stop": EventType.STOP,
    "SubagentStop": EventType.SUBAGENT_STOP,
    "SessionEnd": EventType.SESSION_END,
}

SHELL_TOOL = rendering.SHELL_TOOL
PATCH_TOOL = "apply_patch"
# Core vocabulary for a file removal. Not one of Claude Code's tools: Claude deletes
# through Bash. Anything that is not read-only is validated, and PostToolUse records its
# ``file_path`` as changed, which is what a deletion is.
DELETE_TOOL = "Delete"

# Files larger than this are not read to work out an update's effect. The edit is still
# evaluated (scope, risk) — only its evidence is left unknown.
MAX_READ_BYTES = 2_000_000

_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash", "fish"}
_SHELL_SCRIPT_FLAG = re.compile(r"-[a-z]*c[a-z]*")
_EXIT_HEADER = re.compile(r"\AExit code: (-?\d+)\n(?:.*\n)*?Output:\n", re.MULTILINE)

_STRICTNESS = {
    DecisionAction.ALLOW: 0,
    DecisionAction.MODIFY: 1,
    DecisionAction.REQUEST_REVIEW: 2,
    DecisionAction.CHALLENGE: 3,
    DecisionAction.BLOCK: 4,
}


# -- shell commands -----------------------------------------------------------------


def shell_command(tool_input: Any) -> str | None:
    """The command string a shell tool will run, whatever shape Codex sent it in."""
    value = tool_input.get("command") if isinstance(tool_input, dict) else tool_input
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and all(isinstance(arg, str) for arg in value):
        if (
            len(value) == 3
            and Path(value[0]).name in _SHELLS
            and _SHELL_SCRIPT_FLAG.fullmatch(value[1])
        ):
            return value[2]
        return shlex.join(value)
    return None


def shell_result(tool_response: Any) -> Any:
    """Codex's Bash result, in the adapter result contract.

    ``{"stdout": str, "exit_code": int | None, "interrupted": bool}``. Codex 0.166.0 sends
    only the output text, so ``exit_code`` is None ("unknown", never "succeeded") unless an
    ``Exit code:`` header is present. Today's core reads this shape already: the text via
    ``runners.output_text``, the exit code only when it is an int.
    """
    if not isinstance(tool_response, str):
        return tool_response
    match = _EXIT_HEADER.match(tool_response)
    if match:
        output = tool_response[match.end() :]
        return {"stdout": output, "exit_code": int(match.group(1)), "interrupted": False}
    return {"stdout": tool_response, "exit_code": None, "interrupted": False}


def is_read_only_command(command: str) -> bool:
    """Whether the core counts a shell command as read-only: the core's own classifier
    (``validate.checks.read_only`` over ``validate.shell.parse``), never a second one.

    The adapter does not act on it: every Bash call goes to the core, which applies this
    same classifier itself, after its Level-0 checks (module docstring). It stays here for
    callers and tests that ask the question directly. Unsure means False.
    """
    if not isinstance(command, str) or not command.strip():
        return False
    return checks.read_only(shell.parse(command))


# -- payload -> events --------------------------------------------------------------


def _base(payload: dict[str, Any], event_type: EventType) -> dict[str, Any]:
    return {
        "event": event_type,
        "agent": AGENT_NAME,
        "workspace": payload.get("cwd") or ".",
        "session_id": payload.get("session_id") or "",
        "tool_use_id": payload.get("tool_use_id"),
        "prompt_text": payload.get("prompt"),
        "last_assistant_message": payload.get("last_assistant_message"),
        "raw": payload,
    }


def to_events(payload: dict[str, Any], root: Path | None = None) -> list[AgentEvent]:
    """Codex hook payload -> zero or more AgentEvents (several only for a multi-file patch).

    ``root`` is the repository root used to confine file reads when working out what an
    update hunk does; it is resolved from ``cwd`` when omitted.
    """
    event_type = EVENT_MAP.get(payload.get("hook_event_name", ""))
    if event_type is None:
        return []
    base = _base(payload, event_type)
    if event_type not in (EventType.PRE_TOOL_USE, EventType.POST_TOOL_USE):
        return [AgentEvent(**base)]

    pre = event_type is EventType.PRE_TOOL_USE
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    response = payload.get("tool_response")
    if tool == SHELL_TOOL:
        # Every command, reads included: the core classifies it (module docstring).
        command = shell_command(tool_input)
        return [
            AgentEvent(
                **base,
                tool=SHELL_TOOL,
                arguments={"command": command} if command is not None else {},
                result=shell_result(response),
            )
        ]
    if tool == PATCH_TOOL:
        return _patch_events(payload, base, tool_input, response, root)
    if pre:
        return []  # unknown or MCP tool: never judged as a write
    return [
        AgentEvent(
            **base,
            tool=tool if isinstance(tool, str) and tool else "unknown",
            arguments={"input": tool_input},
            result=response,
        )
    ]


def to_event(payload: dict[str, Any]) -> AgentEvent | None:
    """API parity with the Claude adapter: the first event, or None when ignored."""
    events = to_events(payload)
    return events[0] if events else None


def _patch_events(
    payload: dict[str, Any],
    base: dict[str, Any],
    tool_input: Any,
    response: Any,
    root: Path | None,
) -> list[AgentEvent]:
    text = tool_input.get("command") if isinstance(tool_input, dict) else tool_input
    try:
        ops = patchlib.parse_patch(text)
    except patchlib.PatchError:
        # Codex validates patches before PreToolUse, so this means the port disagrees with
        # Codex. Keep the event for the log, with no edit semantics: unknown stays unknown.
        return [AgentEvent(**base, tool=PATCH_TOOL, arguments={"input": tool_input}, result=response)]

    cwd = Path(str(payload.get("cwd") or ".")).expanduser()
    pre = base["event"] is EventType.PRE_TOOL_USE
    specs: list[tuple[str, dict[str, Any]]] = []
    for op in ops:
        path = _absolute(cwd, op.path)
        if op.kind == "add":
            specs.append(("Write", {"file_path": path, "content": op.contents}))
        elif op.kind == "delete":
            specs.append((DELETE_TOOL, {"file_path": path}))
        elif op.move_to is not None:
            destination: dict[str, Any] = {"file_path": _absolute(cwd, op.move_to)}
            if pre:
                original = _read_original(cwd, root, path)
                new_text = patchlib.apply_chunks(original, op.chunks) if original is not None else None
                if new_text is not None:
                    destination["content"] = new_text
            specs.append(("Write", destination))
            specs.append((DELETE_TOOL, {"file_path": path}))
        else:
            specs.append(_update_spec(cwd, root, path, op.chunks, pre))

    tool_use_id = base.get("tool_use_id")
    events = []
    for index, (tool, arguments) in enumerate(specs):
        fields = dict(base)
        if len(specs) > 1 and tool_use_id:
            fields["tool_use_id"] = f"{tool_use_id}#{index}"
        events.append(AgentEvent(**fields, tool=tool, arguments=arguments, result=response))
    return events


def _update_spec(
    cwd: Path, root: Path | None, path: str, chunks: list[patchlib.Chunk], pre: bool
) -> tuple[str, dict[str, Any]]:
    pairs = None
    if pre:
        original = _read_original(cwd, root, path)
        if original is not None:
            pairs = patchlib.edit_pairs(original, chunks)
    if pairs is None:
        # The file could not be read or located here; describe the hunks literally. The
        # evidence engine will most likely find nothing to apply them to, and say nothing.
        pairs = [(_join(chunk.old_lines), _join(chunk.new_lines)) for chunk in chunks] or [("", "")]
    if len(pairs) == 1:
        old, new = pairs[0]
        return "Edit", {"file_path": path, "old_string": old, "new_string": new}
    return "MultiEdit", {
        "file_path": path,
        "edits": [{"old_string": old, "new_string": new} for old, new in pairs],
    }


def _join(lines: list[str]) -> str:
    return "".join(line + "\n" for line in lines)


def _absolute(cwd: Path, raw: str) -> str:
    candidate = Path(raw).expanduser()
    return str(candidate if candidate.is_absolute() else cwd / candidate)


def _read_original(cwd: Path, root: Path | None, path: str) -> str | None:
    """The file's current text, read the same way the evidence engine reads it.

    Confined to the repository: an absolute path elsewhere, ``..`` traversal or a symlink
    leading out of the workspace yields None, never a read.
    """
    try:
        if root is None:
            from agentguard.repo.gitinfo import repository_root

            root = repository_root(cwd)
        base = Path(root).resolve(strict=False)
        rel = relative_path(base, path)
        if rel is None:
            return None
        full = base / rel
        if not full.resolve(strict=False).is_relative_to(base):
            return None
        if not full.is_file() or full.stat().st_size > MAX_READ_BYTES:
            return None
        # Same call as `evidence.extractors.resolve_edit`, so both see identical text.
        return full.read_text(encoding="utf-8", errors="replace")
    except (OSError, RuntimeError, ValueError):
        return None


# -- decision -> Codex output -------------------------------------------------------


def from_decision(event: AgentEvent, decision: Decision, hook_name: str) -> dict[str, Any]:
    """Decision -> Codex hook stdout JSON. ``{}`` means "no opinion" (print nothing)."""
    return rendering.render(event, decision, hook_name)


# -- several file events -> one answer ----------------------------------------------


def _label(event: AgentEvent) -> str:
    path = event.arg("file_path")
    if not isinstance(path, str) or not path:
        return event.tool or "this action"
    try:
        rel = relative_path(Path(event.workspace), path)
    except (OSError, ValueError):
        rel = None
    return rel or path


def _strictness(pair: tuple[AgentEvent, Decision]) -> tuple[int, int]:
    """Rank by action, then by what observe mode says the action would have been (every
    observe-mode decision is an ALLOW, so the would-have is what tells them apart)."""
    decision = pair[1]
    would_have = decision.would_have
    return _STRICTNESS[decision.action], _STRICTNESS[would_have] if would_have is not None else -1


def combine(results: list[tuple[AgentEvent, Decision]]) -> tuple[AgentEvent, Decision]:
    """One decision for a multi-file patch: the strictest wins, every concern is kept.

    Each file was evaluated (and recorded) on its own. What goes back to Codex has to be a
    single answer, so it takes the strictest action of any file, and its reason lists the
    concern for each file that had one — so the agent can address all of them at once
    rather than discovering them one retry at a time.

    The answer *is* the strictest file's decision, copied, with only these fields merged:
    the reason (every concern, labelled), findings, level, latency, context, and

    * ``signoff_required`` — true if any file needs the developer's sign-off, together
      with that file's ``signoff_code`` where decisions carry one. A sign-off must never
      be lost on the way to a heuristic (``render.is_irreversible``) that may not
      recognise it;
    * ``would_have`` — the strictest of the files' would-haves (observe mode);
    * ``updated_arguments`` — always dropped. A rewrite belongs to one action, and a
      multi-file answer must never apply one file's rewrite to another.

    Every other field — ``unverified_finish``, and any field added to ``Decision`` later —
    rides along from the strictest decision unchanged.
    """
    if len(results) == 1:
        return results[0]
    ranked = sorted(results, key=_strictness, reverse=True)  # stable: file order breaks ties
    strictest_event, strictest = ranked[0]
    concerns = [
        (event, decision)
        for event, decision in results
        if decision.action is not DecisionAction.ALLOW and (decision.reason or "").strip()
    ]
    if len(concerns) > 1:
        reason = f"AgentGuard checked each file in this patch; {len(concerns)} need attention.\n\n" + (
            "\n\n".join(f"[{_label(event)}]\n{decision.reason.strip()}" for event, decision in concerns)
        )
    elif concerns:
        event, decision = concerns[0]
        reason = f"[{_label(event)}]\n{decision.reason.strip()}"
    else:
        reason = strictest.reason
    contexts = [d.additional_context for _, d in results if d.additional_context]
    would_haves = [d.would_have for _, d in results if d.would_have is not None]
    would_have = max(would_haves, key=_STRICTNESS.__getitem__) if would_haves else None
    update: dict[str, Any] = {
        "reason": reason,
        "findings": [finding for _, decision in results for finding in decision.findings],
        "level": max(decision.level for _, decision in results),
        "latency_ms": sum(decision.latency_ms for _, decision in results),
        "additional_context": "\n\n".join(dict.fromkeys(contexts)) or None,
        "updated_arguments": None,
        "would_have": would_have,
    }
    signoff = next((d for _, d in ranked if d.signoff_required), None)
    if signoff is not None:
        update["signoff_required"] = True
        # The one-shot sign-off code travels with the file that needs it. Read through
        # getattr: the field is newer than this adapter, and a decision type without it
        # simply has nothing to carry.
        if "signoff_code" in type(strictest).model_fields:
            update["signoff_code"] = getattr(signoff, "signoff_code", None)
    return strictest_event, strictest.model_copy(update=update, deep=True)


def handle_payload(guard: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """The daemon entry point for ``/hook/codex``. Never raises past the daemon's guard.

    A plain event goes through ``Guard.handle`` once. A multi-file patch goes through it
    once per file — so each file is checked, recorded and attributed on its own — and the
    answers are combined.
    """
    hook_name = payload.get("hook_event_name", "")
    if hook_name not in EVENT_MAP or not guard.settings.enabled:
        return {}
    root: Path | None = None
    if hook_name == "PreToolUse" and payload.get("tool_name") == PATCH_TOOL:
        try:
            root = Path(guard.workspace(payload.get("cwd") or ".").root)
        except Exception:  # noqa: BLE001 - no root just means update evidence stays unknown
            root = None
    events = to_events(payload, root=root)
    if not events:
        return {}
    results = [(event, guard.handle(event)) for event in events]
    event, decision = combine(results)
    return from_decision(event, decision, hook_name)
