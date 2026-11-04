"""Run the Claude Code plugin's hooks the way Claude Code runs them.

`hooks/hooks.json` is the contract, so tests drive *it* rather than calling the scripts
behind it directly: select the groups whose matcher accepts the tool, substitute the path
placeholders, and spawn each command as a shell-form hook (``sh -c``) with the payload on
stdin and the plugin variables exported — what the hooks reference documents for plugin
command hooks.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "agentguard-claude"
HOOKS_FILE = PLUGIN_ROOT / "hooks" / "hooks.json"
MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
HOOK_SCRIPT = PLUGIN_ROOT / "scripts" / "hook.sh"

_EXACT = re.compile(r"^[A-Za-z0-9_\-\s,|]*$")


def load_hooks() -> dict:
    return json.loads(HOOKS_FILE.read_text(encoding="utf-8"))["hooks"]


def matcher_accepts(matcher: str | None, value: str | None) -> bool:
    """Claude Code's matcher rules: empty/"*" match all; plain names are an exact list
    (``|`` or ``,`` separated); anything else is an unanchored JavaScript regex."""
    if matcher in (None, "", "*"):
        return True
    if _EXACT.match(matcher):
        names = {part.strip() for part in re.split(r"[|,]", matcher) if part.strip()}
        return value in names
    return re.search(matcher, value or "") is not None


@dataclass
class HookRun:
    command: str
    returncode: int
    stdout: str
    stderr: str
    ms: float

    @property
    def output(self) -> dict:
        return json.loads(self.stdout) if self.stdout.strip() else {}


def plugin_env(data: Path, project: Path, home: Path, **extra: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AGENTGUARD_", "CLAUDE_PLUGIN_"))
    }
    env.update(
        CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT),
        CLAUDE_PLUGIN_DATA=str(data),
        CLAUDE_PROJECT_DIR=str(project),
        AGENTGUARD_HOME=str(home),
    )
    env.update(extra)
    return env


def run_event(
    event: str,
    payload: dict,
    env: dict[str, str],
    timeout: float = 120.0,
) -> list[HookRun]:
    """Every hook that would fire for ``payload``, run in declaration order."""
    runs = []
    tool = payload.get("tool_name")
    match_value = tool if event.startswith(("PreToolUse", "PostToolUse")) else payload.get("source")
    for group in load_hooks().get(event, []):
        if not matcher_accepts(group.get("matcher"), match_value):
            continue
        for hook in group["hooks"]:
            command = (
                hook["command"]
                .replace("${CLAUDE_PLUGIN_ROOT}", env["CLAUDE_PLUGIN_ROOT"])
                .replace("${CLAUDE_PLUGIN_DATA}", env["CLAUDE_PLUGIN_DATA"])
            )
            started = time.perf_counter()
            done = subprocess.run(
                ["/bin/sh", "-c", command],
                input=json.dumps({**payload, "hook_event_name": event}).encode(),
                capture_output=True,
                env=env,
                cwd=env["CLAUDE_PROJECT_DIR"],
                timeout=timeout,
                check=False,
            )
            runs.append(
                HookRun(
                    command=command,
                    returncode=done.returncode,
                    stdout=done.stdout.decode("utf-8", "replace"),
                    stderr=done.stderr.decode("utf-8", "replace"),
                    ms=(time.perf_counter() - started) * 1000,
                )
            )
    return runs
