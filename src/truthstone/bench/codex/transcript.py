"""Read what happened in a cell: the ``codex exec --json`` stream and the session rollout.

Two sources, because neither is complete. The exec stream carries every shell command
with its **exit code** (which Codex's hooks do not), every file change and the final
message. The rollout carries the pinned settings as Codex applied them (model, effort,
sandbox), per-request token usage, the plan's usage windows, and the model-visible traces
of hooks: a ``PreToolUse`` denial inside a tool's output, a Stop continuation as a
``<hook_prompt>`` user message, and injected developer context.

Nothing here scores an outcome. These are process facts and manipulation checks. Account
identifiers in ``session_meta`` are never copied out.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from truthstone.bench.codex import naming

_SHELL_WRAPPERS = {"sh", "bash", "zsh", "dash"}
_TEST_COMMAND = re.compile(r"(?:^|[\s;&|(/])(?:python3?\s+-m\s+)?(pytest|py\.test|unittest)(?=\s|$|;|&|\|)")
_NARROWING = re.compile(r"(::|\s-k\s|\s-k=|--deselect|--lf\b|--last-failed|\s--sw\b|--stepwise)")
_INSTALL = re.compile(
    r"\b(pip3?|python3?\s+-m\s+pip)\s+install\b|\buv\s+(pip\s+install|add)\b|\bpoetry\s+add\b"
)
# The harness's own list of commands worth noting. Deliberately independent of the
# product's classifier: these are descriptive process facts, never grades.
_RISKY = re.compile(
    r"\bgit\s+clean\s+-\w*f|\bgit\s+reset\s+--hard|\bchmod\s+(-R\s+)?[0-7]*7[0-7]*7\b|"
    r"\bDROP\s+(TABLE|DATABASE)\b|\brm\s+-\w*r\w*\s",
    re.IGNORECASE,
)
_HOOK_DENIAL = re.compile(r"blocked by PreToolUse hook:?\s*(.*)", re.IGNORECASE)
_USAGE_LIMIT = re.compile(
    r"usage limit|rate limit|too many requests|\b429\b|quota exceeded|purchase more credits|"
    r"upgrade to (plus|pro)|hit your (usage )?limit",
    re.IGNORECASE,
)


def is_guard_context(text: str) -> bool:
    """A developer message the guard injected (its planning budget or a hook's context).

    Codex's own context blocks are tagged (``<skills_instructions>``, ``<environment_context>``
    ...), and its skills listing names the plugin's skill in *both* arms by design. Hook
    context arrives as raw text in the product's own voice. Counting every message that
    merely mentions the product flagged the skills listing as an observe-only leak in the
    first smoke run, which was a false alarm.
    """
    stripped = text.lstrip()
    return not stripped.startswith("<") and bool(naming.MODEL_VISIBLE_MARKER.search(stripped[:400]))


def unwrap_command(command: str) -> str:
    """``/bin/zsh -lc 'pytest -q'`` -> ``pytest -q``. Anything else is returned as is."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return command
    if len(argv) == 3 and Path(argv[0]).name in _SHELL_WRAPPERS and argv[1] in ("-lc", "-c", "-l"):
        return argv[2]
    return command


@dataclass(slots=True)
class CommandRun:
    index: int
    command: str
    exit_code: int | None
    status: str


@dataclass(slots=True)
class TestRun:
    index: int
    command: str
    scope: str  # "full" | "narrowed"
    exit_code: int | None

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(slots=True)
class Transcript:
    thread_id: str = ""
    final_message: str | None = None
    commands: list[CommandRun] = field(default_factory=list)
    file_changes: list[tuple[int, str, str]] = field(default_factory=list)  # (index, path, kind)
    test_runs: list[TestRun] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    turns_completed: int = 0
    # rollout
    cli_version: str = ""
    model: str = ""
    effort: str = ""
    sandbox: str = ""
    sandbox_network: bool | None = None  # the rollout's sandbox_policy.network_access
    approval_policy: str = ""
    service_tier: str = ""
    model_requests: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    rate_limits_first: dict | None = None
    rate_limits_last: dict | None = None
    visible_denials: list[str] = field(default_factory=list)
    stop_continuations: list[str] = field(default_factory=list)
    guard_context_messages: int = 0
    duration_ms: int | None = None
    # Claude Code: a PostToolUse objection the model reads after a tool ran.
    post_tool_feedback: list[str] = field(default_factory=list)
    hook_events_reported: dict[str, int] = field(default_factory=dict)

    # -- derived process facts ---------------------------------------------------------

    @property
    def last_edit_index(self) -> int:
        return max((i for i, _, _ in self.file_changes), default=-1)

    @property
    def ran_tests(self) -> bool:
        return bool(self.test_runs)

    def runs_after_last_edit(self) -> list[TestRun]:
        return [run for run in self.test_runs if run.index > self.last_edit_index]

    @property
    def verified_full_after_last_edit(self) -> bool:
        return any(run.scope == "full" for run in self.runs_after_last_edit())

    @property
    def last_run_passed(self) -> bool | None:
        return self.test_runs[-1].passed if self.test_runs else None

    @property
    def narrowed_only_after_last_edit(self) -> bool:
        after = self.runs_after_last_edit()
        return bool(after) and all(run.scope == "narrowed" for run in after)

    @property
    def install_attempts(self) -> list[str]:
        return [c.command for c in self.commands if _INSTALL.search(c.command)]

    @property
    def risky_commands(self) -> list[str]:
        return [c.command for c in self.commands if _RISKY.search(c.command)]

    @property
    def usage_limit_hit(self) -> bool:
        if any(_USAGE_LIMIT.search(e) for e in self.errors):
            return True
        last = self.rate_limits_last or {}
        return bool(last.get("rate_limit_reached_type"))

    def process_facts(self) -> dict[str, Any]:
        return {
            "ran_tests": self.ran_tests,
            "test_runs": len(self.test_runs),
            "verified_full_after_last_edit": self.verified_full_after_last_edit,
            "narrowed_only_after_last_edit": self.narrowed_only_after_last_edit,
            "last_run_passed": self.last_run_passed,
            "edits": len(self.file_changes),
            "commands": len(self.commands),
            "install_attempts": len(self.install_attempts),
            "risky_commands": self.risky_commands[:10],
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["process"] = self.process_facts()
        return data


_VALUE_OPTIONS = {
    "-c",
    "-p",
    "-o",
    "-W",
    "-r",
    "--rootdir",
    "--tb",
    "--maxfail",
    "--basetemp",
    "--import-mode",
    "--confcutdir",
    "--durations",
    "-s",
    "-t",  # unittest discover: -s start dir, -t top dir
}
_NARROWING_OPTIONS = {"-k", "-m", "--deselect", "--lf", "--last-failed", "--sw", "--stepwise", "-P"}
_WHOLE_TREE = {"tests", "test", ".", "src", "discover"}


def classify_test_command(command: str) -> str | None:
    """``full`` or ``narrowed`` for a test command; ``None`` for anything else.

    Narrowed means the run could not have exercised the whole suite: a ``-k`` or marker
    selection, a ``::node`` id, last-failed modes, or a positional path other than the
    test tree itself.
    """
    if not _TEST_COMMAND.search(command):
        return None
    segment = next((s for s in re.split(r"&&|\|\||;|\|", command) if _TEST_COMMAND.search(s)), command)
    try:
        argv = shlex.split(segment)
    except ValueError:
        return "narrowed" if _NARROWING.search(f" {segment} ") else "full"
    start = None
    for i, token in enumerate(argv):
        name = Path(token).name
        if name in ("pytest", "py.test"):
            start = i + 1
            break
        if token == "-m" and i + 1 < len(argv) and argv[i + 1] in ("pytest", "unittest"):
            start = i + 2
            break
    if start is None:
        return None  # "pytest" appeared, but not as the program being run
    skip = False
    for arg in argv[start:]:
        if skip:
            skip = False
            continue
        option = arg.split("=", 1)[0]
        if option in _NARROWING_OPTIONS:
            return "narrowed"
        if arg in _VALUE_OPTIONS:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        if "::" in arg:
            return "narrowed"
        if arg.rstrip("/") in _WHOLE_TREE:
            continue
        return "narrowed"
    return "full"


def read_exec_stream(path: Path, transcript: Transcript | None = None) -> Transcript:
    """Parse the JSONL ``codex exec --json`` wrote to stdout."""
    t = transcript or Transcript()
    if not path.exists():
        return t
    index = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "thread.started":
            t.thread_id = str(event.get("thread_id", ""))
        elif kind == "turn.completed":
            t.turns_completed += 1
        elif kind == "turn.failed":
            t.errors.append(str((event.get("error") or {}).get("message", "turn failed")))
        elif kind == "error":
            t.errors.append(str(event.get("message", "error")))
        elif kind == "item.completed":
            item = event.get("item") or {}
            index += 1
            itype = item.get("type")
            if itype == "agent_message":
                t.final_message = str(item.get("text", ""))
            elif itype == "command_execution":
                command = unwrap_command(str(item.get("command", "")))
                exit_code = item.get("exit_code")
                t.commands.append(CommandRun(index, command, exit_code, str(item.get("status", ""))))
                scope = classify_test_command(command)
                if scope:
                    t.test_runs.append(TestRun(index, command, scope, exit_code))
            elif itype == "file_change" and item.get("status") == "completed":
                for change in item.get("changes") or []:
                    t.file_changes.append((index, str(change.get("path", "")), str(change.get("kind", ""))))
            elif itype == "error":
                t.errors.append(str(item.get("message", "")))
    return t


def _texts(content: Any) -> list[str]:
    out: list[str] = []
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    out.append(text)
            elif isinstance(part, str):
                out.append(part)
    return out


def _window(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    return {k: raw.get(k) for k in ("used_percent", "window_minutes", "resets_at")}


def read_rollout(path: Path | None, transcript: Transcript | None = None) -> Transcript:
    """Parse a session rollout. Copies settings and counts; never identities."""
    t = transcript or Transcript()
    if path is None or not path.exists():
        return t
    totals: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        rtype = record.get("type")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        ptype = payload.get("type")
        if rtype == "session_meta":
            t.cli_version = str(payload.get("cli_version", ""))
        elif rtype == "turn_context":
            t.model = str(payload.get("model", t.model))
            t.approval_policy = str(payload.get("approval_policy", ""))
            sandbox = payload.get("sandbox_policy")
            if isinstance(sandbox, dict):
                t.sandbox = str(sandbox.get("type", ""))
                if isinstance(sandbox.get("network_access"), bool):
                    t.sandbox_network = sandbox["network_access"]
        elif rtype == "token_usage_record":
            t.model_requests += 1
            usage = payload.get("usage") or {}
            for key, value in usage.items():
                if isinstance(value, int):
                    totals[key] = totals.get(key, 0) + value
        elif rtype == "event_msg" and ptype == "thread_settings_applied":
            settings = payload.get("thread_settings") or {}
            t.effort = str(settings.get("reasoning_effort", t.effort))
            t.model = str(settings.get("model", t.model))
            tier = settings.get("service_tier")
            if tier is not None:
                t.service_tier = str(tier)
        elif rtype == "event_msg" and ptype == "token_count":
            limits = payload.get("rate_limits")
            if isinstance(limits, dict):
                snapshot = {
                    "primary": _window(limits.get("primary")),
                    "secondary": _window(limits.get("secondary")),
                    "plan_type": limits.get("plan_type"),
                    "rate_limit_reached_type": limits.get("rate_limit_reached_type"),
                }
                if t.rate_limits_first is None:
                    t.rate_limits_first = snapshot
                t.rate_limits_last = snapshot
        elif rtype == "event_msg" and ptype == "task_complete":
            t.duration_ms = payload.get("duration_ms")
            last = payload.get("last_agent_message")
            if isinstance(last, str) and last.strip():
                t.final_message = last
        elif rtype == "event_msg" and ptype in ("error", "stream_error"):
            t.errors.append(str(payload.get("message", ptype)))
        elif rtype == "response_item" and ptype == "message":
            role = payload.get("role")
            for text in _texts(payload.get("content")):
                if role == "user" and text.lstrip().startswith("<hook_prompt"):
                    t.stop_continuations.append(text[:2000])
                elif role == "developer" and is_guard_context(text):
                    t.guard_context_messages += 1
        elif rtype == "response_item" and ptype in ("custom_tool_call_output", "function_call_output"):
            for text in _texts(payload.get("output")):
                match = _HOOK_DENIAL.search(text)
                if match:
                    t.visible_denials.append(match.group(1)[:2000])
    t.usage = totals
    return t


def find_rollout(codex_home: Path, thread_id: str = "") -> Path | None:
    candidates = sorted((codex_home / "sessions").glob("**/rollout-*.jsonl"))
    if thread_id:
        exact = [c for c in candidates if thread_id in c.name]
        if exact:
            return exact[-1]
    return candidates[-1] if candidates else None


_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _hook_json(stdout: str) -> dict:
    try:
        data = json.loads(stdout) if stdout and stdout.strip().startswith("{") else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def read_claude_stream(path: Path, transcript: Transcript | None = None) -> Transcript:
    """Parse ``claude -p --output-format stream-json --verbose --include-hook-events``.

    Claude Code reports every hook run (``system/hook_response`` with its stdout), so the
    model-visible interventions are read from what the hooks actually returned: a
    PreToolUse ``deny``, a Stop ``block``, an ``additionalContext``. A ``systemMessage``
    is shown to the developer, never to the model, and does not count.
    """
    t = transcript or Transcript()
    if not path.exists():
        return t
    totals: dict[str, int] = {}
    seen_requests: set[str] = set()
    pending: dict[str, tuple[int, str, str]] = {}  # tool_use_id -> (index, tool, command)
    index = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind, subtype = event.get("type"), event.get("subtype")
        if kind == "system" and subtype == "init":
            t.thread_id = str(event.get("session_id", ""))
            t.cli_version = str(event.get("claude_code_version", ""))
            t.model = str(event.get("model", ""))
            t.approval_policy = str(event.get("permissionMode", ""))
        elif kind == "assistant":
            message = event.get("message") or {}
            request = str(message.get("id") or event.get("request_id") or "")
            if request and request not in seen_requests:
                seen_requests.add(request)
                usage = message.get("usage") or {}
                # Codex's convention, so one estimator serves both hosts: input_tokens is all
                # input (uncached + cache reads + cache writes); the parts are broken out.
                totals["input_tokens"] = totals.get("input_tokens", 0) + sum(
                    int(usage.get(k) or 0)
                    for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
                )
                totals["cached_input_tokens"] = totals.get("cached_input_tokens", 0) + int(
                    usage.get("cache_read_input_tokens") or 0
                )
                totals["cache_write_input_tokens"] = totals.get("cache_write_input_tokens", 0) + int(
                    usage.get("cache_creation_input_tokens") or 0
                )
                totals["output_tokens"] = totals.get("output_tokens", 0) + int(
                    usage.get("output_tokens") or 0
                )
            for part in message.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = str(part.get("text", ""))
                    if text.lstrip().startswith("API Error"):
                        t.errors.append(text[:500])  # retries exhausted: infrastructure, not the agent
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                index += 1
                name = str(part.get("name", ""))
                arguments = part.get("input") or {}
                if name in _EDIT_TOOLS and isinstance(arguments.get("file_path"), str):
                    t.file_changes.append((index, arguments["file_path"], name.lower()))
                elif name == "Bash" and isinstance(arguments.get("command"), str):
                    pending[str(part.get("id", ""))] = (index, name, arguments["command"])
        elif kind == "user":
            message = event.get("message") or {}
            for part in message.get("content") or []:
                if not isinstance(part, dict) or part.get("type") != "tool_result":
                    continue
                entry = pending.pop(str(part.get("tool_use_id", "")), None)
                if entry is None:
                    continue
                position, _name, command = entry
                exit_code = 1 if part.get("is_error") else 0
                t.commands.append(
                    CommandRun(position, command, exit_code, "failed" if exit_code else "completed")
                )
                scope = classify_test_command(command)
                if scope:
                    t.test_runs.append(TestRun(position, command, scope, exit_code))
        elif kind == "system" and subtype == "hook_response":
            raw = str(event.get("stdout") or event.get("output") or "")
            output = _hook_json(raw)
            hook_event = str(event.get("hook_event") or "")
            t.hook_events_reported[hook_event] = t.hook_events_reported.get(hook_event, 0) + 1
            specific = output.get("hookSpecificOutput") or {}
            reason = str(output.get("reason") or specific.get("permissionDecisionReason") or "")
            if event.get("exit_code") == 2:
                # Exit 2: Claude Code feeds stderr to the model (a block in every event here).
                output, reason = {"decision": "block"}, str(event.get("stderr") or "")
            if hook_event == "Stop" and output.get("decision") == "block":
                t.stop_continuations.append(reason[:2000])
            elif hook_event == "PreToolUse" and (
                specific.get("permissionDecision") in ("deny", "ask") or output.get("decision") == "block"
            ):
                # Headless, an ask has nobody to answer it: Claude Code refuses the call and
                # the model reads the reason. Model-visible either way.
                t.visible_denials.append(reason[:2000])
            elif hook_event in ("PostToolUse", "PostToolUseFailure") and output.get("decision") == "block":
                t.post_tool_feedback.append(reason[:2000])
            elif output.get("decision") == "block":
                t.visible_denials.append(reason[:2000])
            context = specific.get("additionalContext")
            # Only the guard's plugin and the harness's silent logging hook are loaded, so any
            # injected context is the guard's. Plain stdout is context on these two events.
            if (isinstance(context, str) and context.strip()) or (
                not output
                and raw.strip()
                and hook_event in ("SessionStart", "UserPromptSubmit")
                and event.get("exit_code") in (0, None)
            ):
                t.guard_context_messages += 1
        elif kind == "rate_limit_event":
            info = event.get("rate_limit_info") or {}
            windows = info.get("unifiedWindows") or {}

            def window(raw: Any) -> dict | None:
                if not isinstance(raw, dict):
                    return None
                used = raw.get("utilization")
                return {
                    "used_percent": round(float(used) * 100, 2) if isinstance(used, (int, float)) else None,
                    "resets_at": raw.get("resetsAt"),
                    "status": raw.get("status"),
                }

            rejected = info.get("status") == "rejected"
            snapshot = {
                "primary": window(windows.get("five_hour")),
                "secondary": window(windows.get("seven_day")),
                "status": info.get("status"),
                "rate_limit_reached_type": (info.get("rateLimitType") or "unknown") if rejected else None,
                "using_overage": bool(info.get("isUsingOverage")),
                "overage_status": info.get("overageStatus"),
            }
            if t.rate_limits_first is None:
                t.rate_limits_first = snapshot
            t.rate_limits_last = snapshot
        elif kind == "result":
            t.duration_ms = event.get("duration_ms")
            if isinstance(event.get("result"), str):
                t.final_message = event["result"]
            if event.get("is_error") or str(subtype or "").startswith("error"):
                t.errors.append(str(event.get("result") or subtype or "error"))
            elif subtype == "success":
                t.turns_completed += 1
            t.model_requests = len(seen_requests)
    if seen_requests:
        t.model_requests = len(seen_requests)
    t.usage = totals
    return t


def read_cell(exec_stream: Path, codex_home: Path | None, last_message: Path | None = None) -> Transcript:
    t = read_exec_stream(exec_stream)
    rollout = find_rollout(codex_home, t.thread_id) if codex_home else None
    t = read_rollout(rollout, t)
    if last_message is not None and last_message.exists():
        text = last_message.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            t.final_message = text
    return t
