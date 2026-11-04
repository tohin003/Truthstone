"""A minimal client for ``codex app-server`` (JSON-RPC over stdio, one object per line).

Three jobs, none of which sends a prompt to a model:

* ``hooks/list`` — every hook Codex would run for a working directory, with its key,
  current hash and trust status;
* trust — exactly what the TUI's ``/hooks`` "trust" button does: ``config/batchWrite``
  upserting ``hooks.state.<key>.trusted_hash`` with the hash ``hooks/list`` reported
  (verified live by the Codex adapter's builder on codex-cli 0.166.0);
* ``account/rateLimits/read`` — the plan's 5-hour and weekly usage windows.

It refuses to run without an explicit, isolated ``CODEX_HOME``: the user's own
``~/.codex`` must never be written by the benchmark.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class AppServerError(RuntimeError):
    pass


def assert_isolated_home(env: dict[str, str]) -> Path:
    home = env.get("CODEX_HOME")
    if not home:
        raise AppServerError("refusing to start codex app-server without an explicit CODEX_HOME")
    resolved = Path(home).expanduser().resolve()
    if resolved == (Path.home() / ".codex").resolve():
        raise AppServerError("refusing to use the user's own ~/.codex as a benchmark home")
    return resolved


class AppServer:
    def __init__(self, codex_bin: str, env: dict[str, str], cwd: Path | None = None, timeout: float = 60.0):
        assert_isolated_home(env)
        self.timeout = timeout
        self._proc = subprocess.Popen(
            [codex_bin, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(cwd) if cwd else None,
            text=True,
            bufsize=1,
        )
        self._next = 1
        self._responses: dict[int, dict] = {}
        self._cond = threading.Condition()
        self._closed = False
        threading.Thread(target=self._reader, daemon=True).start()

    # -- plumbing -----------------------------------------------------------------

    def _reader(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and "id" in message and ("result" in message or "error" in message):
                with self._cond:
                    self._responses[message["id"]] = message
                    self._cond.notify_all()
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _send(self, message: dict) -> None:
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AppServerError(f"app-server is not accepting input: {exc}") from exc

    def call(self, method: str, params: dict | None = None, timeout: float | None = None) -> Any:
        request_id = self._next
        self._next += 1
        message: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)
        deadline = time.monotonic() + (timeout or self.timeout)
        with self._cond:
            while request_id not in self._responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppServerError(f"{method}: no answer within {timeout or self.timeout}s")
                if self._closed:
                    raise AppServerError(f"{method}: app-server exited")
                self._cond.wait(remaining)
            response = self._responses.pop(request_id)
        if "error" in response:
            raise AppServerError(f"{method}: {response['error']}")
        return response.get("result")

    def notify(self, method: str, params: dict | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def close(self) -> None:
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.wait(timeout=10)
        except Exception:  # noqa: BLE001 - shutting down a helper process must not raise
            self._proc.kill()

    def __enter__(self) -> AppServer:
        self.call("initialize", {"clientInfo": {"name": "bench", "title": "bench", "version": "0.1.0"}})
        self.notify("initialized")
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- the three jobs -------------------------------------------------------------

    def hooks(self, cwd: Path) -> list[dict]:
        listing = self.call("hooks/list", {"cwds": [str(cwd)]}) or {}
        return [hook for entry in listing.get("data") or [] for hook in entry.get("hooks") or []]

    def trust(self, hooks: list[dict]) -> Any:
        updates = {hook["key"]: {"trusted_hash": hook["currentHash"]} for hook in hooks}
        if not updates:
            return None
        return self.call(
            "config/batchWrite",
            {
                "edits": [{"keyPath": "hooks.state", "value": updates, "mergeStrategy": "upsert"}],
                "reloadUserConfig": True,
            },
        )

    def rate_limits(self) -> dict:
        return self.call("account/rateLimits/read", None) or {}


def trust_status(hook: dict) -> str:
    return str(hook.get("trustStatus", "")).lower()


def establish_trust(
    server: AppServer,
    cwd: Path,
    select: Callable[[dict], bool],
) -> tuple[list[dict], list[dict]]:
    """Trust every selected hook that is not yet trusted; return (selected, others).

    Re-lists after writing so the caller asserts on what Codex now reports, not on what
    was written.
    """
    hooks = server.hooks(cwd)
    pending = [h for h in hooks if select(h) and trust_status(h) not in ("trusted", "managed")]
    if pending:
        server.trust(pending)
        hooks = server.hooks(cwd)
    selected = [h for h in hooks if select(h)]
    others = [h for h in hooks if not select(h)]
    return selected, others


def isolated_env(base: dict[str, str]) -> dict[str, str]:
    """A copy of ``base`` that keeps only what codex needs to find its home and login."""
    keep = ("PATH", "HOME", "CODEX_HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL")
    return {k: v for k, v in base.items() if k in keep and v} | {"NO_COLOR": "1"}


def plan_type_and_windows(result: dict) -> dict[str, Any]:
    """Normalise ``account/rateLimits/read`` into snake_case windows."""
    limits = result.get("rateLimits") or {}

    def window(raw: Any) -> dict | None:
        if not isinstance(raw, dict):
            return None
        return {
            "used_percent": raw.get("usedPercent"),
            "window_minutes": raw.get("windowDurationMins"),
            "resets_at": raw.get("resetsAt"),
        }

    return {
        "plan_type": limits.get("planType"),
        "primary": window(limits.get("primary")),
        "secondary": window(limits.get("secondary")),
        "limit_reached": limits.get("rateLimitReachedType"),
        "ordinary_usage_allowed": result.get("ordinaryUsageAllowed"),
        "read_at": time.time(),
    }


__all__ = [
    "AppServer",
    "AppServerError",
    "assert_isolated_home",
    "establish_trust",
    "isolated_env",
    "plan_type_and_windows",
    "trust_status",
]
