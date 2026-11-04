"""What ``agentguard doctor`` can find out about Codex — read-only.

Hook *trust* is the part that matters most and is easiest to get wrong: Codex skips
untrusted hooks, in ``codex exec`` without a word. The authoritative answer comes from
Codex itself, through the same ``hooks/list`` call its ``/hooks`` panel makes, so that is
what this asks. It never writes trust: approving hooks is the developer's decision.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentguard import names
from agentguard.adapters.codex import plugin as plugin_meta
from agentguard.adapters.codex.install import HOOK_MODULE, codex_home


@dataclass(slots=True)
class HookTrust:
    key: str
    event: str
    trust: str  # trusted | untrusted | modified | managed
    enabled: bool
    plugin_id: str | None


@dataclass(slots=True)
class TrustReport:
    hooks: list[HookTrust] = field(default_factory=list)
    error: str = ""

    @property
    def needs_review(self) -> list[HookTrust]:
        return [h for h in self.hooks if h.enabled and h.trust not in ("trusted", "managed")]


def codex_version(executable: str | None = None) -> str | None:
    exe = executable or shutil.which("codex")
    if not exe:
        return None
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None


def plugin_id() -> str:
    return f"{plugin_meta.PLUGIN_NAME}@{plugin_meta.MARKETPLACE_NAME}"


def plugin_enabled(home: Path | None = None) -> bool | None:
    """True/False from ``[plugins."<id>"].enabled``; None when the plugin is not configured."""
    path = (home or codex_home()) / "config.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    entry = (data.get("plugins") or {}).get(plugin_id())
    if not isinstance(entry, dict):
        return None
    return bool(entry.get("enabled", True))


def plugin_installed(home: Path | None = None) -> bool:
    # Codex installs plugins into plugins/cache/<marketplace>/<plugin>/<version>/.
    cache = (home or codex_home()) / "plugins" / "cache" / plugin_meta.MARKETPLACE_NAME
    cache = cache / plugin_meta.PLUGIN_NAME
    return cache.is_dir() and any(cache.iterdir())


def former_plugin_ids(home: Path | None = None) -> list[str]:
    """The plugin under a former product name, wherever Codex still has it installed."""
    cache = (home or codex_home()) / "plugins" / "cache"
    found = []
    for former in names.FORMER:
        marketplace = names.as_former(plugin_meta.MARKETPLACE_NAME, former)
        plugin = names.as_former(plugin_meta.PLUGIN_NAME, former)
        directory = cache / marketplace / plugin
        if directory.is_dir() and any(directory.iterdir()):
            found.append(f"{plugin}@{marketplace}")
    return found


def _is_agentguard(hook: dict[str, Any]) -> bool:
    if hook.get("pluginId") in names.variants(plugin_id()):
        return True
    command = hook.get("command")
    return isinstance(command, str) and any(module in command for module in names.variants(HOOK_MODULE))


def hook_trust(cwd: Path, timeout: float = 30.0, executable: str | None = None) -> TrustReport:
    """Ask Codex (``codex app-server`` ``hooks/list``) how it rates AgentGuard's hooks."""
    exe = executable or shutil.which("codex")
    if not exe:
        return TrustReport(error="codex is not on PATH")
    try:
        proc = subprocess.Popen(
            [exe, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=dict(os.environ),
        )
    except OSError as exc:
        return TrustReport(error=f"could not start codex app-server: {exc}")

    responses: dict[int, dict[str, Any]] = {}
    ready = threading.Condition()

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and isinstance(message.get("id"), int):
                with ready:
                    responses[message["id"]] = message
                    ready.notify_all()

    threading.Thread(target=reader, daemon=True).start()

    def call(request_id: int, method: str, params: dict[str, Any], deadline: float) -> dict[str, Any]:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
        proc.stdin.flush()
        with ready:
            while request_id not in responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(method)
                ready.wait(remaining)
            message = responses.pop(request_id)
        if "error" in message:
            raise RuntimeError(f"{method}: {message['error']}")
        return message.get("result") or {}

    deadline = time.monotonic() + timeout
    try:
        client = {"name": "agentguard_doctor", "title": "agentguard doctor", "version": "1"}
        call(1, "initialize", {"clientInfo": client}, deadline)
        assert proc.stdin is not None
        proc.stdin.write(json.dumps({"method": "initialized"}) + "\n")
        proc.stdin.flush()
        listing = call(2, "hooks/list", {"cwds": [str(cwd)]}, deadline)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return TrustReport(error=f"codex app-server did not answer hooks/list ({exc})")
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()

    report = TrustReport()
    for entry in listing.get("data") or []:
        for hook in entry.get("hooks") or []:
            if isinstance(hook, dict) and _is_agentguard(hook):
                report.hooks.append(
                    HookTrust(
                        key=str(hook.get("key", "")),
                        event=str(hook.get("eventName", "")),
                        trust=str(hook.get("trustStatus", "")).lower(),
                        enabled=bool(hook.get("enabled", True)),
                        plugin_id=hook.get("pluginId"),
                    )
                )
    return report
