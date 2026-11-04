"""Agent drivers: the real ``codex exec``, and a scripted stand-in for dry runs.

Both write the same artifacts into a cell directory, so everything downstream (reading,
attesting, grading, analysis) is exercised identically by a dry run.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from truthstone.bench.codex import scripted, suite


@dataclass(slots=True)
class AgentRun:
    exit_code: int | None
    duration_s: float
    timed_out: bool
    stdout_path: Path
    stderr_path: Path
    last_message_path: Path
    argv: list[str]

    def stderr_tail(self, limit: int = 4000) -> str:
        try:
            return self.stderr_path.read_text(encoding="utf-8", errors="replace")[-limit:]
        except OSError:
            return ""


@dataclass(frozen=True, slots=True)
class CodexSettings:
    """Pinned per plan; identical in both arms."""

    model: str
    effort: str
    reasoning_summary: str = "none"
    service_tier: str = "default"  # explicit standard routing: Fast mode can never apply
    sandbox: str = "workspace-write"
    network: bool = False
    timeout_s: int = 1200


class CodexExecAgent:
    def __init__(self, codex_bin: str, settings: CodexSettings):
        self.codex_bin = codex_bin
        self.settings = settings

    def argv(self, prompt: str, repo: Path, tmpdir: Path, last_message: Path, extra: list[str]) -> list[str]:
        s = self.settings
        return [
            self.codex_bin,
            "exec",
            "--json",
            "-o",
            str(last_message),
            "-m",
            s.model,
            "-c",
            f'model_reasoning_effort="{s.effort}"',
            "-c",
            f'model_reasoning_summary="{s.reasoning_summary}"',
            "-c",
            f'service_tier="{s.service_tier}"',
            "-c",
            'approval_policy="never"',
            "-s",
            s.sandbox,
            "-c",
            f"sandbox_workspace_write.network_access={'true' if s.network else 'false'}",
            "--add-dir",
            str(tmpdir),
            "-C",
            str(repo),
            *extra,
            prompt,
        ]

    def run(
        self,
        prompt: str,
        repo: Path,
        env: dict[str, str],
        cell_dir: Path,
        tmpdir: Path,
        extra: list[str],
        **_: object,
    ) -> AgentRun:
        stdout_path = cell_dir / "exec.jsonl"
        stderr_path = cell_dir / "exec.stderr"
        last = cell_dir / "last_message.txt"
        argv = self.argv(prompt, repo, tmpdir, last, extra)
        started = time.monotonic()
        timed_out = False
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            proc = subprocess.Popen(
                argv,
                cwd=repo,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            try:
                proc.wait(timeout=self.settings.timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc)
        return AgentRun(
            proc.returncode,
            time.monotonic() - started,
            timed_out,
            stdout_path,
            stderr_path,
            last,
            [*argv[:-1], "<prompt>"],
        )


def _kill_group(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


# -- the scripted stand-in --------------------------------------------------------

# (task, phrasing, replicate, arm) -> (variant, simulated guard behaviour)
Policy = Callable[[suite.Task, str, int, str], tuple[str, str]]


def dry_run_policy(
    seed: int = 7, base_fc: float = 0.45, catch: float = 0.7, false_block: float = 0.3
) -> Policy:
    """A *simulated* guard effect, so the dry run can prove the analysis finds a known one.

    Observe arm: the planted false completion with probability ``base_fc`` on opportunity
    tasks. Guarded arm: the same draw, except that on tasks with a mechanism the guard
    "catches" it with probability ``catch`` (the agent then does the honest thing). On
    controls both arms are honest; the guarded arm suffers a simulated false block with
    probability ``false_block``. These numbers are inventions for plumbing, never results.
    """
    import random

    def policy(task: suite.Task, phrasing: str, replicate: int, arm: str) -> tuple[str, str]:
        rng = random.Random(f"{seed}|{task.id}|{phrasing}|{replicate}")
        planted = rng.random() < base_fc
        caught = rng.random() < catch and "none" not in task.opportunity.mechanisms
        blocked = rng.random() < false_block
        if task.set == "control":
            return "honest", ("false_block" if blocked and arm == "on" else "quiet")
        if not planted:
            return "honest", "quiet"
        if arm == "on" and caught:
            return "honest", "caught"
        return "planted", ("missed" if arm == "on" else "would_catch" if caught else "quiet")

    return policy


class ScriptedAgent:
    """Applies a task's scripted solution and writes Codex-shaped artifacts."""

    def __init__(
        self,
        policy: Policy,
        python: str,
        model: str = "scripted",
        effort: str = "medium",
        host: str = "codex",
        accounts: Any = None,
        interrupt: set[str] | None = None,
        permission_mode: str = "bypassPermissions",
    ):
        self.policy = policy
        self.python = python
        self.model = model
        self.effort = effort
        self.host = host
        self.accounts = accounts  # claude.FakeAccounts: what each cell spends
        self.interrupt = set(interrupt or ())  # pair ids whose next cell hits a usage limit
        self.permission_mode = permission_mode

    def _claude_stream(
        self,
        cell_dir: Path,
        message: str,
        continued: bool,
        observe_only: bool,
        account: str | None,
        interrupted: bool,
    ) -> Path:
        """What ``claude -p --output-format stream-json --include-hook-events`` would print."""
        session = f"scripted-{cell_dir.name}"
        usage = {
            "input_tokens": 8,
            "cache_read_input_tokens": 30000,
            "cache_creation_input_tokens": 1500,
            "output_tokens": 450,
        }
        events: list[dict] = [
            {
                "type": "system",
                "subtype": "init",
                "session_id": session,
                "model": self.model,
                "permissionMode": self.permission_mode,
                "claude_code_version": "scripted",
                "tools": ["Bash", "Edit"],
            },
            {
                "type": "system",
                "subtype": "hook_response",
                "hook_event": "SessionStart",
                "stdout": "",
                "exit_code": 0,
                "outcome": "success",
            },
            {
                "type": "system",
                "subtype": "hook_response",
                "hook_event": "UserPromptSubmit",
                "stdout": "",
                "exit_code": 0,
                "outcome": "success",
            },
        ]
        requests = 6 + (3 if continued else 0)
        for number in range(requests):
            content: list[dict] = [{"type": "text", "text": "working"}]
            if number == 1:
                content = [
                    {
                        "type": "tool_use",
                        "id": "toolu_test",
                        "name": "Bash",
                        "input": {"command": "python -m pytest -q"},
                    }
                ]
            events.append(
                {
                    "type": "assistant",
                    "message": {
                        "id": f"msg_{number}",
                        "model": self.model,
                        "content": content,
                        "usage": usage,
                    },
                }
            )
            if number == 1:
                events.append(
                    {
                        "type": "user",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "toolu_test",
                                    "is_error": False,
                                    "content": "ok",
                                }
                            ]
                        },
                    }
                )
        if continued and not observe_only:
            reason = "Truthstone — completion gate: incomplete (scripted)"
            events.append(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "Stop",
                    "stdout": json.dumps({"decision": "block", "reason": reason}),
                    "exit_code": 0,
                    "outcome": "success",
                }
            )
        reading = self.accounts.spend(account) if (self.accounts is not None and account) else None
        if reading is not None:
            session_used = reading["session"]["used_percent"] / 100
            events.append(
                {
                    "type": "rate_limit_event",
                    "rate_limit_info": {
                        "status": "rejected" if interrupted else "allowed",
                        "rateLimitType": "five_hour",
                        "overageStatus": "rejected",
                        "isUsingOverage": False,
                        "unifiedWindows": {
                            "five_hour": {
                                "utilization": 1.0 if interrupted else session_used,
                                "resetsAt": int(reading["session"]["resets_at"]),
                                "status": "allowed",
                            },
                            "seven_day": {
                                "utilization": reading["week"]["used_percent"] / 100,
                                "resetsAt": int(reading["week"]["resets_at"]),
                                "status": "allowed",
                            },
                        },
                    },
                }
            )
        if interrupted:
            events.append(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": True,
                    "duration_ms": 900,
                    "result": "You've hit your limit · resets 4pm (UTC)",
                    "usage": usage,
                }
            )
        else:
            events.append(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": 1000,
                    "result": message,
                    "usage": usage,
                }
            )
        path = cell_dir / "stream.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        (cell_dir / "claude.stderr").write_text("", encoding="utf-8")
        return path

    def _rollout(self, cell_dir: Path, message: str, continued: bool, observe_only: bool) -> None:
        def line(record: dict) -> str:
            return json.dumps(record)

        records = [
            {"type": "session_meta", "payload": {"cli_version": "scripted"}},
            {
                "type": "turn_context",
                "payload": {
                    "model": self.model,
                    "approval_policy": "never",
                    "sandbox_policy": {"type": "workspace-write"},
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "thread_settings_applied",
                    "thread_settings": {"model": self.model, "reasoning_effort": self.effort},
                },
            },
        ]
        requests = 6 + (3 if continued else 0)
        for _ in range(requests):
            records.append(
                {
                    "type": "token_usage_record",
                    "payload": {
                        "usage": {
                            "input_tokens": 20000,
                            "cached_input_tokens": 17000,
                            "output_tokens": 400,
                            "reasoning_output_tokens": 120,
                        }
                    },
                }
            )
        records.append(
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {"used_percent": 1.0, "window_minutes": 300, "resets_at": 0},
                        "secondary": {"used_percent": 2.0, "window_minutes": 10080, "resets_at": 0},
                        "plan_type": "plus",
                        "rate_limit_reached_type": None,
                    },
                },
            }
        )
        if continued and not observe_only:
            records.append(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": '<hook_prompt hook_run_id="stop:1">'
                                "Truthstone — completion gate: incomplete</hook_prompt>",
                            }
                        ],
                    },
                }
            )
        records.append(
            {
                "type": "event_msg",
                "payload": {"type": "task_complete", "duration_ms": 1000, "last_agent_message": message},
            }
        )
        (cell_dir / "rollout.jsonl").write_text("\n".join(line(r) for r in records) + "\n", encoding="utf-8")

    def run(
        self,
        prompt: str,
        repo: Path,
        env: dict[str, str],
        cell_dir: Path,
        tmpdir: Path,
        extra: list[str],
        *,
        task: suite.Task,
        phrasing: str,
        replicate: int,
        arm: str,
        trace_dir: Path,
        observe_only: bool,
        account: str | None = None,
        **_: object,
    ) -> AgentRun:
        started = time.monotonic()
        variant, behaviour = self.policy(task, phrasing, replicate, arm)
        pair_id = f"{task.id}|{phrasing}|r{replicate}"
        interrupted = self.host == "claude" and pair_id in self.interrupt
        self.interrupt.discard(pair_id)
        ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")
        # A guard that "caught" a false completion held a Stop on the planted state; the
        # agent then did the honest thing. Snapshot that first attempt, as the logging
        # hook would have, so the dry run's false-block metric sees a true hold.
        first_attempt: tuple[Path, str] | None = None
        if behaviour == "caught" and not observe_only:
            scratch = trace_dir.parent / "first-attempt"
            shutil.copytree(repo, scratch, ignore=ignore)
            first_attempt = (scratch, scripted.run_solution(task, "planted", scratch, self.python))
        message = scripted.run_solution(task, variant, repo, self.python)
        thread = f"scripted-{task.id}-{phrasing}-{replicate}-{arm}"
        stdout_path = cell_dir / "exec.jsonl"
        events = [
            {"type": "thread.started", "thread_id": thread},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "i1",
                    "type": "command_execution",
                    "command": "/bin/zsh -lc 'python -m pytest -q'",
                    "aggregated_output": "",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": message}},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 60000,
                    "cached_input_tokens": 50000,
                    "output_tokens": 3000,
                    "reasoning_output_tokens": 800,
                },
            },
        ]
        stdout_path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        (cell_dir / "exec.stderr").write_text("", encoding="utf-8")
        last = cell_dir / "last_message.txt"
        last.write_text(message, encoding="utf-8")

        # What the hooks would have recorded.
        trace_dir.mkdir(parents=True, exist_ok=True)
        acted = behaviour in ("caught", "false_block")
        would = behaviour in ("would_catch",)
        stop_decision = {
            "event_type": "stop",
            "tool": None,
            "latency_ms": 2.0,
            "ts": time.time(),
            "action": "block" if acted and not observe_only else "allow",
            "would_have": "block" if (acted and observe_only) or would else "",
            "reason": "Truthstone — completion gate: incomplete (scripted)" if acted or would else "",
        }
        decisions = [
            {
                "event_type": "user_prompt",
                "action": "allow",
                "would_have": "",
                "latency_ms": 3.0,
                "ts": time.time(),
            },
            stop_decision,
        ]
        if acted and not observe_only:
            decisions.append({**stop_decision, "action": "allow", "would_have": "", "reason": ""})
        evidence = {
            "events": {
                "session_start": 1,
                "user_prompt": 1,
                "pre_tool_use": 2,
                "post_tool_use": 2,
                "stop": 2 if acted and not observe_only else 1,
            },
            "sessions": [{"id": thread, "observe_only": observe_only}],
            "decisions": decisions,
            "findings": [],
        }
        (trace_dir / "fake-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
        # The logging hook's view: one Stop snapshot per Stop event, in order.
        stops: list[tuple[Path, str]] = []
        if first_attempt is not None:
            stops.append(first_attempt)
        elif acted and not observe_only:
            stops.append((repo, message))  # a false block: the held state was already right
        stops.append((repo, message))  # the final Stop
        reported: dict[str, Any] = {}
        if self.host == "claude":  # Claude Code tells its hooks the effort and permission mode
            reported = {
                "model": None,
                "effort": {"level": self.effort},
                "permission_mode": self.permission_mode,
            }
        with (trace_dir / "hooks.jsonl").open("a", encoding="utf-8") as handle:
            for event in ("SessionStart", "UserPromptSubmit"):
                handle.write(
                    json.dumps({"ts": time.time(), "event": event, "elapsed_ms": 1.0, **reported}) + "\n"
                )
            for number, (tree, said) in enumerate(stops[: 2 if acted and not observe_only else 1], start=1):
                shutil.copytree(tree, trace_dir / f"stop-{number}", ignore=ignore)
                record = {
                    "ts": time.time(),
                    "event": "Stop",
                    "elapsed_ms": 1.0,
                    "snapshot": f"stop-{number}",
                    "stop_hook_active": number > 1,
                    "last_assistant_message": said,
                }
                handle.write(json.dumps(record) + "\n")
        if first_attempt is not None:
            shutil.rmtree(first_attempt[0], ignore_errors=True)
        shutil.rmtree(repo / ".pytest_cache", ignore_errors=True)
        if self.host == "claude":
            stdout_path.unlink(missing_ok=True)
            (cell_dir / "exec.stderr").unlink(missing_ok=True)
            stream = self._claude_stream(cell_dir, message, acted, observe_only, account, interrupted)
            if interrupted:
                last.unlink(missing_ok=True)
            return AgentRun(
                1 if interrupted else 0,
                time.monotonic() - started,
                False,
                stream,
                cell_dir / "claude.stderr",
                last,
                ["scripted", variant, behaviour],
            )
        self._rollout(cell_dir, message, continued=acted, observe_only=observe_only)
        return AgentRun(
            0,
            time.monotonic() - started,
            False,
            stdout_path,
            cell_dir / "exec.stderr",
            last,
            ["scripted", variant, behaviour],
        )
