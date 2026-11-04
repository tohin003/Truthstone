"""Codex command hook: stdin JSON -> local daemon -> stdout JSON.

Codex has no ``http`` hook type (codex-rs 0.166.0 knows ``command``, ``mcp_tool``,
``prompt`` and ``agent``, and skips the last two), so every Codex hook is a process:
``$SHELL -lc "<command>"`` with the payload on stdin. This module is that process, and it
is built to cost as little as a process can:

* stdlib only, and only ``json``/``os``/``socket``/``sys`` on the hot path. ``http.client``
  alone costs ~15 ms to import (it pulls in ``email``), so the request is written by hand:
  one ``POST /hook/codex``, ``Connection: close``, read to EOF.
* no ``/health`` probe before a tool call; a dead PID in the handshake is skipped for free
  and anything else that goes wrong simply means "no decision".

Lifecycle work happens only where a process spawn is invisible: ``session-start`` starts
the daemon if needed, and ``user-prompt-submit`` revives it once if it died. If neither
can bring it up, the developer is told once per session (``systemMessage``) that the
session is unguarded — failing open is required, failing open *silently* is not. A daemon
that answers but guards less than it seems (switched off, observe-only, or any ``/health``
degraded reason) is reported the same way: once per session per reason, keyed on the
reason's ``code``, with the Claude shim's notices and marker files (R9).

Every path exits 0. Codex treats exit 2 as "block, reason on stderr", so a guard that
exited 2 on its own failure would block the very work it should never impede.
"""

from __future__ import annotations

import json
import os
import socket
import sys

# `os` and `stat` only (no pathlib): where the home is, by the rule every entry point shares.
from agentguard.daemon import private_paths

MAX_STDIN_BYTES = 1_000_000
MAX_RESPONSE_BYTES = 256_000
HOT_PATH_TIMEOUT_S = 4.0
LIFECYCLE_TIMEOUT_S = 10.0

# argv[1] -> the Codex event it is installed on. The payload's own `hook_event_name` is
# authoritative; the argument only selects lifecycle behaviour (and documents the hook).
EVENTS = {
    "session-start": "SessionStart",
    "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
    "subagent-stop": "SubagentStop",
    "session-end": "SessionEnd",
}

UNGUARDED_NOTICE = (
    "AgentGuard could not reach or start its local daemon, so this Codex session is "
    "UNGUARDED. Run `agentguard doctor` to see why; `agentguard daemon start` restarts it. "
    "Your work continues either way."
)
STALE_DAEMON_NOTICE = (
    "The running AgentGuard daemon (pid {pid}) predates Codex support, so this Codex session "
    "is UNGUARDED. Restart it: `agentguard daemon stop && agentguard daemon start`."
)


def _home() -> str:
    """The home the daemon uses: resolved through trusted symlinks, by the rule every
    entry point shares (R11)."""
    return private_paths.home()


def _disabled() -> bool:
    return os.environ.get("AGENTGUARD_DISABLE", "").strip().lower() in {"1", "true", "yes", "on"}


def _handshake() -> dict | None:
    home, trusted = private_paths.resolve_home(private_paths.configured_home())
    if not trusted:
        return None  # behind a link someone else could swap: not the daemon's handshake
    path = os.path.join(home, "daemon.json")
    try:
        if os.path.islink(path):
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.loads(fh.read(64_000))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _endpoint(hs: dict) -> tuple[str, int] | None:
    """Only an IPv4 loopback endpoint is ever contacted (no `ipaddress` import needed)."""
    host = hs.get("host", "127.0.0.1")
    if host == "localhost":
        host = "127.0.0.1"
    parts = host.split(".") if isinstance(host, str) else []
    if len(parts) != 4 or parts[0] != "127" or not all(p.isdigit() and int(p) < 256 for p in parts):
        return None
    port = hs.get("port")
    if type(port) is not int or not 0 < port <= 65535:
        return None
    return host, port


def _pid_alive(hs: dict) -> bool:
    pid = hs.get("pid")
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, OverflowError, ValueError):
        return False
    return True


def post(hs: dict, body: bytes, timeout: float = HOT_PATH_TIMEOUT_S) -> dict:
    """POST the raw payload to the daemon's Codex route. ``{}`` on any failure."""
    endpoint = _endpoint(hs)
    token = hs.get("token")
    if endpoint is None or not isinstance(token, str) or not token or "\n" in token or "\r" in token:
        return {}
    host, port = endpoint
    request = (
        f"POST /hook/codex HTTP/1.1\r\nHost: {host}:{port}\r\n"
        f"Content-Type: application/json\r\nAuthorization: Bearer {token}\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode("ascii") + body
    chunks: list[bytes] = []
    size = 0
    try:
        with socket.create_connection((host, port), timeout=timeout) as conn:
            conn.sendall(request)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    return {}
                chunks.append(chunk)
    except OSError:
        return {}
    head, sep, payload = b"".join(chunks).partition(b"\r\n\r\n")
    if not sep:
        return {}
    status_line = head.split(b"\r\n", 1)[0].split()
    if len(status_line) < 2 or status_line[1] != b"200":
        return {}
    if b"transfer-encoding: chunked" in head.lower():
        return {}  # the daemon always sends Content-Length; anything else is not ours
    try:
        out = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def _notify_once(session_id: str) -> bool:
    """True the first time this session is warned. A repeated warning is just nagging."""
    safe = "".join(c for c in (session_id or "unknown") if c.isalnum() or c in "-_")[:64]
    marker = os.path.join(_home(), f"codex-notified-{safe}")
    try:
        from agentguard.daemon.lifecycle import create_private_marker

        return bool(create_private_marker(marker, str(os.getpid())))
    except Exception:  # noqa: BLE001 - if the marker cannot be written, warn rather than hide
        return True


def _health(hs: dict | None) -> dict | None:
    """``GET /health``, accepted only from the daemon the handshake names (pid match)."""
    if not hs or not _pid_alive(hs):
        return None
    endpoint = _endpoint(hs)
    if endpoint is None:
        return None
    import http.client  # lifecycle path only: ~15 ms of imports the hot path never pays

    conn = http.client.HTTPConnection(*endpoint, timeout=1.0)
    try:
        conn.request("GET", "/health")
        response = conn.getresponse()
        if response.status != 200:
            return None
        body = json.loads(response.read(64_000).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - unreachable, wrong service, garbage: all "not ours"
        return None
    finally:
        conn.close()
    return body if isinstance(body, dict) and body.get("pid") == hs.get("pid") else None


def _lifecycle() -> tuple[dict | None, str, dict | None]:
    """Make sure a daemon that speaks Codex is up. Returns (handshake, notice, health)."""
    hs = _handshake()
    health = _health(hs)
    if health is None:
        # The daemon-start logic (inter-process lock, detached spawn, readiness wait) is
        # host-neutral; reuse it rather than keep a second copy.
        from agentguard.adapters.claude_code import shim

        hs = shim.ensure_daemon()
        health = _health(hs)
    if hs is None or health is None:
        return None, UNGUARDED_NOTICE, None
    adapters = health.get("adapters")
    if not isinstance(adapters, list) or "codex" not in adapters:
        return None, STALE_DAEMON_NOTICE.format(pid=hs.get("pid")), health
    return hs, "", health


def _daemon_notices(health: dict | None, session_id: str) -> list[str]:
    """Why a daemon that answers still guards less than it seems, once per session per
    reason (R9): switched off, observe-only, and each ``/health`` degraded reason, keyed on
    its ``code``. The same notices and marker files as the Claude shim; never raises."""
    if not health:
        return []
    try:
        from agentguard.adapters.claude_code import protocol, shim

        return shim.pending_notices(health, session_id, protocol.session_mode_from_env(os.environ))
    except Exception:  # noqa: BLE001 - a notice that cannot be worked out is not worth a failure
        return []


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    except (OSError, ValueError):
        return 0
    if len(raw) > MAX_STDIN_BYTES:
        return 0
    try:
        payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (UnicodeDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict) or _disabled():
        return 0

    hook = payload.get("hook_event_name") or EVENTS.get(args[0] if args else "", "")
    session_id = str(payload.get("session_id") or "")
    health: dict | None = None
    if hook in ("SessionStart", "UserPromptSubmit"):
        try:
            hs, notice, health = _lifecycle()
        except Exception:  # noqa: BLE001 - lifecycle problems must never break the session
            hs, notice, health = None, UNGUARDED_NOTICE, None
        if hs is None:
            if _notify_once(session_id):
                sys.stdout.write(json.dumps({"systemMessage": notice}))
            return 0
        timeout = LIFECYCLE_TIMEOUT_S
    else:
        hs = _handshake()
        if hs is None or not _pid_alive(hs):
            return 0  # fail open, silently: this runs on every tool call
        timeout = HOT_PATH_TIMEOUT_S

    try:
        out = post(hs, raw, timeout=timeout)
    except Exception:  # noqa: BLE001 - any transport failure means "no decision"
        out = {}
    # Lifecycle events only: the hot path never pays for /health or a marker file.
    notices = _daemon_notices(health, session_id)
    if notices:
        out = dict(out)
        earlier = out.get("systemMessage")
        told = "\n".join(notices)
        out["systemMessage"] = f"{earlier}\n{told}" if isinstance(earlier, str) and earlier else told
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
