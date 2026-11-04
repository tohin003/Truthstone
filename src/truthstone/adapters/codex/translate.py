"""Codex ⇄ Truthstone translation.

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
``Bash``. A command that is unambiguously read-only (``is_read_only_command``) is not sent
through the core's pre-tool checks, so scope and evidence checks never fire on a read. Its
PostToolUse is still recorded. Anything the classifier is not sure about is validated.

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

from truthstone.adapters.codex import patch as patchlib
from truthstone.adapters.codex import render as rendering
from truthstone.core.enums import DecisionAction, EventType
from truthstone.core.events import AgentEvent
from truthstone.core.models import Decision
from truthstone.repo.paths import relative_path

AGENT_NAME = "codex"

# Codex hook event name -> normalized event type. PermissionRequest is deliberately
# absent: answering it would mean granting or refusing permissions, and Truthstone
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


# Commands that only read. Deliberately short: a command missing from here is simply
# validated, which costs a little latency and nothing else.
_READ_ONLY = frozenset(
    {
        "cat", "head", "tail", "wc", "ls", "pwd", "echo", "printf", "grep", "egrep", "fgrep",
        "rg", "ag", "tree", "stat", "du", "df", "which", "type", "whereis", "uname", "whoami",
        "id", "basename", "dirname", "realpath", "readlink", "cut", "nl", "od", "hexdump",
        "diff", "cmp", "comm", "jq", "true", "test", "[",
    }
)
_GIT_READ_ONLY = frozenset(
    {"status", "log", "diff", "show", "rev-parse", "ls-files", "blame", "describe", "grep", "shortlog"}
)
_FIND_WRITES = frozenset(
    {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
)
_SED_PRINT = re.compile(r"\d+(,(\d+|\$))?p|\$p")
# Anything that can write, substitute, background or redirect. `&&` and `||` are fine.
_UNSAFE_SHELL = re.compile(r"[<>`]|\$\(|(?<!&)&(?!&)|\btee\b")


def is_read_only_command(command: str) -> bool:
    """Whether a shell command certainly cannot change anything. Unsure means False."""
    if not isinstance(command, str) or not command.strip() or "\n" in command.strip():
        return False
    if _UNSAFE_SHELL.search(command):
        return False
    try:
        tokens = shlex.split(command.replace("&&", " ; ").replace("||", " ; ").replace("|", " ; "))
    except ValueError:
        return False
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token == ";":
            segments.append([])
        else:
            segments[-1].append(token)
    segments = [segment for segment in segments if segment]
    return bool(segments) and all(_segment_is_read_only(segment) for segment in segments)


def _segment_is_read_only(argv: list[str]) -> bool:
    name = argv[0]
    if "=" in name:  # VAR=value prefixes change the environment of what follows
        return False
    if name in _READ_ONLY:
        return True
    if name == "find":
        return not any(arg in _FIND_WRITES for arg in argv[1:])
    if name == "sed":
        flags = [arg for arg in argv[1:] if arg.startswith("-")]
        scripts = [arg for arg in argv[1:] if not arg.startswith("-")]
        return flags == ["-n"] and bool(scripts) and _SED_PRINT.fullmatch(scripts[0]) is not None
    if name == "git":
        rest = argv[1:]
        while rest and rest[0] in ("-C", "--no-pager", "-P"):
            rest = rest[2:] if rest[0] == "-C" else rest[1:]
        if any(arg.startswith("--output") for arg in rest):
            return False  # `git diff --output=FILE` writes
        return bool(rest) and rest[0] in _GIT_READ_ONLY
    return False


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
        command = shell_command(tool_input)
        if pre and command is not None and is_read_only_command(command):
            return []  # a read: nothing for the write-path checks to judge
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
            from truthstone.repo.gitinfo import repository_root

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


def combine(results: list[tuple[AgentEvent, Decision]]) -> tuple[AgentEvent, Decision]:
    """One decision for a multi-file patch: the strictest wins, every concern is kept.

    Each file was evaluated (and recorded) on its own. What goes back to Codex has to be a
    single answer, so it takes the strictest action of any file, and its reason lists the
    concern for each file that had one — so the agent can address all of them at once
    rather than discovering them one retry at a time.
    """
    if len(results) == 1:
        return results[0]
    strictest_event, strictest = max(results, key=lambda pair: _STRICTNESS[pair[1].action])
    concerns = [
        (event, decision)
        for event, decision in results
        if decision.action is not DecisionAction.ALLOW and (decision.reason or "").strip()
    ]
    if len(concerns) > 1:
        reason = f"Truthstone checked each file in this patch; {len(concerns)} need attention.\n\n" + (
            "\n\n".join(f"[{_label(event)}]\n{decision.reason.strip()}" for event, decision in concerns)
        )
    elif concerns:
        event, decision = concerns[0]
        reason = f"[{_label(event)}]\n{decision.reason.strip()}"
    else:
        reason = strictest.reason
    contexts = [d.additional_context for _, d in results if d.additional_context]
    merged = Decision(
        action=strictest.action,
        reason=reason,
        findings=[finding for _, decision in results for finding in decision.findings],
        level=max(decision.level for _, decision in results),
        latency_ms=sum(decision.latency_ms for _, decision in results),
        additional_context="\n\n".join(dict.fromkeys(contexts)) or None,
        decision_id=strictest.decision_id,
    )
    return strictest_event, merged


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
