"""Local AgentGuard daemon (SPEC §30).

    Developer -> Coding Agent -> Local AgentGuard daemon -> Filesystem / Git / AST / tests

Why a daemon at all: the repository index, symbol maps and caches are expensive to build
and cheap to keep. A per-tool-call subprocess would rebuild or reload them constantly and
blow the SPEC §8 latency budget. The daemon holds them warm.

Why HTTP: Claude Code supports `{"type": "http"}` hooks, which it calls itself. That
removes Python interpreter startup (30-80ms) from every single tool call. Binding is
127.0.0.1-only and every request carries a bearer token from a 0600 handshake file.

Hosts: `POST /hook/<name>` is routed through `agentguard.adapters.registry` (H4). The
daemon knows no host's payload or field names; adding a host never means editing it.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import logging
import os
import secrets
import signal
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from agentguard.adapters import registry
from agentguard.core.config import (
    DaemonSettings,
    Settings,
    agentguard_home,
    daemon_config_error,
    daemon_handshake_path,
    ensure_private_dir,
    get_or_create_token,
    write_private_text,
)
from agentguard.core.engine import Guard
from agentguard.core.metrics import METRICS
from agentguard.daemon import degraded, logs
from agentguard.daemon.lifecycle import handshake_lock_path, interprocess_lock

log = logging.getLogger(__name__)

# R9: rejected hook requests are counted over this window and reported by /health.
AUTH_FAILURE_WINDOW_S = 600.0
# Degradation messages are keyed on by the command hooks (once per session per reason),
# so they never embed counts or times; those go in `degraded_detail`.
AUTH_FAILURES_REASON = (
    "hook requests with a missing or wrong token were rejected in the last 10 minutes, so "
    "whatever sent them is not being guarded. If that is a Claude Code session installed "
    "through settings hooks, its token is stale: re-run `agentguard install claude` and "
    "restart that session."
)
OBSERVE_ONLY_REASON = (
    "the daemon is in observe-only mode: it records findings but says nothing, so no session "
    "is guarded (`agentguard observe off`, then restart the daemon)."
)
STORE_REASON = "its storage is degraded, so what it sees may not be recorded: {reason}"
ADAPTER_REASON = "the {name} adapter could not be loaded, so that host's hooks are not judged ({error})."
MAX_HOOK_BODY_BYTES = 1_000_000
MAX_HEALTH_BODY_BYTES = 64_000


def _safe_endpoint(host: Any, port: Any) -> tuple[str, int] | None:
    """Accept only the daemon's loopback IPv4 endpoint from a handshake file."""
    if not isinstance(host, str) or host.strip().lower() == "localhost":
        host = "127.0.0.1"
    try:
        address = ipaddress.ip_address(str(host).strip())
        port_number = int(port)
    except (ValueError, TypeError):
        return None
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_loopback:
        return None
    if not 0 < port_number <= 65535:
        return None
    return str(address), port_number


def write_handshake(host: str, port: int, token: str) -> Path:
    """Publish how to reach the daemon. 0600: the token is a local credential."""
    ensure_private_dir()
    path = daemon_handshake_path()
    payload = {
        "host": host,
        "port": port,
        "token": token,
        "pid": os.getpid(),
        "started_at": time.time(),
        "version": 1,
    }
    # Serialize publication with shutdown cleanup. Without this, an older daemon can
    # finish shutting down after a replacement has published its handshake and unlink
    # the replacement's credentials.
    with interprocess_lock(handshake_lock_path(agentguard_home()), timeout=2.0) as locked:
        if not locked:
            raise RuntimeError("could not claim the daemon handshake lock")
        write_private_text(path, json.dumps(payload, indent=2))
    return path


def read_handshake() -> dict[str, Any] | None:
    try:
        # Validate the full home path before reading credentials.  A symlinked parent
        # can otherwise redirect a seemingly safe daemon.json to another directory.
        ensure_private_dir()
    except (OSError, RuntimeError):
        return None
    path = daemon_handshake_path()
    if path.is_symlink():
        return None
    if not path.exists():
        return None
    try:
        if path.stat().st_size > MAX_HEALTH_BODY_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def clear_handshake(expected_pid: int | None = None, expected_token: str | None = None) -> None:
    """Remove the handshake, optionally only when it still belongs to this daemon.

    Shutdown is racy by nature: a supervisor may start a replacement before the old
    process has finished unwinding.  Matching both PID and token prevents the old
    process from deleting the replacement's handshake.  The lock closes the remaining
    read/replace/unlink window with :func:`write_handshake`.
    """
    path = daemon_handshake_path()
    with interprocess_lock(handshake_lock_path(agentguard_home()), timeout=2.0) as locked:
        if not locked:
            return
        if expected_pid is not None or expected_token is not None:
            current = read_handshake()
            if not current:
                return
            if expected_pid is not None and current.get("pid") != expected_pid:
                return
            if expected_token is not None and current.get("token") != expected_token:
                return
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def daemon_is_alive() -> bool:
    """Whether the daemon in the handshake is actually answering.

    Not a PID check. `daemon.json` outlives a reboot while the process does not, and
    operating systems recycle PIDs, so a stale handshake can name a live but unrelated
    process. Two things then go wrong, and the second is the serious one:

    * `agentguard daemon start` reports "already running" and starts nothing, leaving
      every hook to fail open in silence;
    * `agentguard daemon stop` sends **SIGTERM to that unrelated process**.

    So liveness is defined as "the endpoint answers `/health` and reports the pid we
    expect" — which also rules out something else having claimed the fixed port.
    """
    hs = read_handshake()
    if not hs:
        return False
    pid = hs.get("pid")
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)  # free pre-filter for the common case: the process is simply gone
    except (OSError, ProcessLookupError):
        return False
    return _health_reports(hs, pid)


def _health_reports(hs: dict[str, Any], pid: int) -> bool:
    """`GET /health` on the handshake's endpoint, via stdlib.

    `httpx` is a development dependency, not a runtime one, and this runs inside the CLI.
    """
    import http.client

    endpoint = _safe_endpoint(hs.get("host", "127.0.0.1"), hs.get("port"))
    if endpoint is None:
        return False
    try:
        conn = http.client.HTTPConnection(*endpoint, timeout=1.0)
    except (TypeError, ValueError):
        return False
    try:
        conn.request("GET", "/health")
        response = conn.getresponse()
        if response.status != 200:
            return False
        body = json.loads(response.read(MAX_HEALTH_BODY_BYTES).decode("utf-8", "replace"))
        return isinstance(body, dict) and body.get("pid") == pid
    except Exception:  # noqa: BLE001 - unreachable or not ours: either way, not alive
        return False
    finally:
        with contextlib.suppress(OSError):
            conn.close()


def _store_reasons(guard: Guard) -> list[str]:
    """What the stores say about themselves (``degraded_reason``), when they say anything.

    Read defensively: the attribute may not exist yet, may be a property or a method, and
    the workspace table may change while it is read. None of that may break ``/health``.
    """
    found: list[str] = []
    try:
        workspaces = list(dict(getattr(guard, "_workspaces", {}) or {}).values())
    except Exception:  # noqa: BLE001 - changed while copied: report nothing this time
        return found
    for ws in workspaces:
        store = getattr(ws, "store", None)
        for holder in (store, getattr(store, "db", None)):
            try:
                reason = getattr(holder, "degraded_reason", None)
                if callable(reason):
                    reason = reason()
            except Exception:  # noqa: BLE001 - a store that cannot say is not a new reason
                continue
            if isinstance(reason, str) and reason.strip() and reason.strip() not in found:
                found.append(reason.strip())
    return found


def degradation(app: FastAPI) -> list[degraded.Reason]:
    """Every reason this daemon is guarding less than it seems (R9)."""
    found: list[degraded.Reason] = []
    rejected = app.state.auth_failures.count()
    if rejected:
        detail = {
            "count": rejected,
            "window_s": int(AUTH_FAILURE_WINDOW_S),
            "last_s_ago": app.state.auth_failures.seconds_since_last(),
        }
        found.append(degraded.Reason("auth_failures", AUTH_FAILURES_REASON, detail=detail))
    if app.state.guard.settings.observe_only:
        found.append(degraded.Reason("observe_only", OBSERVE_ONLY_REASON, since=app.state.started_at))
    for index, reason in enumerate(_store_reasons(app.state.guard)):
        code = "store" if index == 0 else f"store-{index + 1}"
        found.append(degraded.Reason(code, STORE_REASON.format(reason=reason[:200])))
    for name, error in registry.load_errors().items():
        found.append(degraded.Reason(f"adapter-{name}", ADAPTER_REASON.format(name=name, error=error)))
    found.extend(degraded.reasons())
    return found


def create_app(token: str, settings: Settings | None = None, guard: Guard | None = None) -> FastAPI:
    app = FastAPI(title="AgentGuard", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.token = token
    app.state.guard = guard or Guard(settings)
    app.state.started_at = time.time()
    # Hook requests refused for their token. Each still gets the fail-open "{}", which is
    # exactly why they must be counted: a stale token is otherwise indistinguishable from
    # a quiet, healthy session (R9).
    app.state.auth_failures = degraded.RecentEvents(AUTH_FAILURE_WINDOW_S)

    def _authorized(authorization: str | None) -> bool:
        """Constant-time comparison of the bearer header, on bytes (R16).

        The server decodes header bytes as latin-1, so a header can hold any character up
        to U+00FF, and ``secrets.compare_digest`` raises ``TypeError`` for non-ASCII
        *strings*. A stray byte in a token therefore turned into a 500 — on ``/hook``
        too, which must answer ``200 {}`` whatever arrives. Bytes have no such limit, and
        ``surrogatepass`` makes the encoding total.
        """
        if not authorization:
            return False
        try:
            presented = authorization.encode("utf-8", "surrogatepass")
            expected = f"Bearer {app.state.token}".encode("utf-8", "surrogatepass")
            return secrets.compare_digest(presented, expected)
        except (TypeError, ValueError):
            return False

    def _check_auth(authorization: str | None) -> None:
        if not _authorized(authorization):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        try:
            reasons = degradation(app)
        except Exception as exc:  # noqa: BLE001 - logged (safely) and reported in the body
            # /health is the liveness probe: it must answer, or a client revives a second
            # daemon. Say that the check itself failed rather than claim all is well.
            log.error("agentguard: degradation check failed\n%s", logs.safe_traceback(exc))
            unknown = "the daemon could not check its own state; see daemon.log"
            reasons = [degraded.Reason("health_check", unknown)]
        return {
            "status": "ok",
            "pid": os.getpid(),
            "uptime_s": round(time.time() - app.state.started_at, 3),
            "enabled": app.state.guard.settings.enabled,
            # The daemon reads config once, at startup. A developer who changed the mode
            # and forgot to restart has no other way to find out which one is live — and
            # the two differ in whether anything is being guarded at all.
            "observing": app.state.guard.settings.observe_only,
            # Which host routes this daemon serves. A daemon started by an older release
            # keeps running across upgrades; a hook for a host it cannot route would get
            # "no opinion" forever, so clients check this before trusting the silence.
            # Only adapters that actually load are listed.
            "adapters": registry.available(),
            # Fail open, but never silently (R9): why this daemon is guarding less than it
            # seems. `degraded` holds one stable message per reason (the command hooks show
            # each once per session); `degraded_detail` adds a stable `code` and counts.
            "degraded": [reason.message for reason in reasons],
            "degraded_detail": [reason.as_json() for reason in reasons],
        }

    @app.get("/metrics")
    async def metrics(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        _check_auth(authorization)
        return METRICS.snapshot()

    @app.post("/hook/{adapter_name}")
    async def hook(
        adapter_name: str, request: Request, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        """The hot path.

        Returns ``{}`` — "no opinion" — on every failure. A guard layer that 500s must
        still not impede the agent (SPEC §39).
        """
        try:
            _check_auth(authorization)
        except HTTPException:
            # Even an auth failure fails open: decide nothing. But count it, because the
            # host cannot tell this "{}" from a healthy one (R9); /health reports it.
            if app.state.auth_failures.note() == 1:
                log.warning(
                    "agentguard: rejected a hook request with a missing or wrong token "
                    "(further rejections within %d minutes are counted in /health, not logged)",
                    int(AUTH_FAILURE_WINDOW_S // 60),
                )
            return JSONResponse({}, status_code=200)

        adapter = registry.get(adapter_name)
        if adapter is None:
            return JSONResponse({}, status_code=200)

        try:
            content_length = request.headers.get("content-length")
            if content_length is not None and int(content_length) > MAX_HOOK_BODY_BYTES:
                return JSONResponse({}, status_code=200)
        except (TypeError, ValueError):
            return JSONResponse({}, status_code=200)

        try:
            chunks: list[bytes] = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_HOOK_BODY_BYTES:
                    return JSONResponse({}, status_code=200)
                chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        except Exception:  # noqa: BLE001 - fail open: unreadable body means "no decision"
            return JSONResponse({}, status_code=200)

        if not isinstance(payload, dict):
            return JSONResponse({}, status_code=200)

        try:
            # An adapter whose one host payload can stand for several actions (a Codex
            # patch editing several files) routes and combines them itself.
            handle_payload = adapter.handle_payload
            if handle_payload is not None:
                out = await run_in_threadpool(handle_payload, app.state.guard, payload)
            else:
                event = adapter.to_event(payload)
                if event is None:
                    return JSONResponse({}, status_code=200)
                # Guard.handle performs synchronous indexing, AST and SQLite work. Running
                # it directly in this async route would stall health checks and every other
                # hook whenever one repository refresh is slow. The Guard serializes state
                # per workspace, so moving it to a worker preserves ordering without
                # blocking the event loop.
                decision = await run_in_threadpool(app.state.guard.handle, event)
                out = adapter.from_decision(event, decision, adapter.hook_name(payload))
            # An adapter bug must not put a non-object on the wire.
            return JSONResponse(out if isinstance(out, dict) else {}, status_code=200)
        except Exception as exc:  # noqa: BLE001 - fail open: logged (safely), then no decision
            # The payload is whatever the agent handled, credentials included, and an
            # exception's text can quote it (pydantic prints `input_value=...`). Log the
            # type and where it happened, never the values (R17).
            log.error(
                "agentguard: hook handling failed on /hook/%s; returning no-decision\n%s",
                adapter_name,
                logs.safe_traceback(exc),
            )
            return JSONResponse({}, status_code=200)

    @app.post("/shutdown")
    async def shutdown(authorization: str | None = Header(default=None)) -> dict[str, str]:
        _check_auth(authorization)
        os.kill(os.getpid(), signal.SIGTERM)
        return {"status": "stopping"}

    return app


def run(host: str | None = None, port: int | None = None, log_level: str = "warning") -> None:
    """Run the daemon in the foreground.

    Defaults come from settings (fixed port, so the installed hook URL stays valid).
    Pass ``port=0`` to grab an ephemeral port — used by tests running daemons in parallel.

    Without an explicit ``port``, an invalid ``[daemon]`` section is refused (exit 2)
    rather than replaced by the default endpoint: the installed hooks post to the port the
    developer configured, so a daemon on 8787 would leave every hook failing open in
    silence (R11). The shim and the CLI spawn ``python -m agentguard.daemon run`` with no
    port, so this is where that path is checked.
    """
    import socket

    import uvicorn

    settings = Settings.load()
    if port is None:
        problem = daemon_config_error(settings)
        if problem:
            sys.stderr.write(f"agentguard: {problem}\n")
            raise SystemExit(2)
    # Before any other work, so the store and the index log through it from the start:
    # one handler for the whole process that never writes a payload value or a secret,
    # rotates daemon.log, and applies `log_level` from config.toml (R11, R17).
    logs.install(settings, agentguard_home() / "daemon.log")
    host = host if host is not None else settings.daemon.host
    port = port if port is not None else settings.daemon.port
    try:
        # Port 0 is useful only for an explicitly foregrounded test process. It must not
        # be accepted from persisted Settings, because an installed hook cannot point at
        # an ephemeral port that changes on every restart.
        ephemeral = port == 0
        endpoint = DaemonSettings(host=host, port=1 if ephemeral else port)
    except Exception as exc:  # invalid config must fail before binding
        sys.stderr.write(f"agentguard: invalid daemon endpoint ({exc})\n")
        raise SystemExit(2) from exc
    host = endpoint.host
    if not ephemeral:
        port = endpoint.port
    token = get_or_create_token()

    # Bind exactly once and retain this socket until uvicorn owns it. A preliminary
    # check followed by close/bind has a check-then-use race: another process can claim
    # the port, and port=0 can be replaced by a different ephemeral port.
    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind((host, port))
    except OSError as exc:
        with contextlib.suppress(OSError):
            listen_socket.close()
        sys.stderr.write(
            f"agentguard: cannot bind {host}:{port} ({exc}). "
            "Change [daemon].port in config.toml and re-run `agentguard install claude`.\n"
        )
        raise SystemExit(1) from exc

    port = int(listen_socket.getsockname()[1])
    app = create_app(token, settings)
    write_handshake(host, port, token)

    ensure_private_dir()
    # `log_config=None`: uvicorn's loggers propagate to the root handler `logs.install`
    # put there, so they are redacted and rotated like everything else.
    config = uvicorn.Config(
        app, host=host, port=port, log_level=log_level, access_log=False, log_config=None
    )
    server = uvicorn.Server(config)

    # uvicorn 0.52 does not unwind the stack on SIGTERM, so a `finally` alone never
    # runs and the handshake file is left behind. Asking the server to exit instead
    # gives a real graceful shutdown. (A stale handshake is still handled correctly
    # everywhere — see `daemon_is_alive()` — because SIGKILL and crashes exist.)
    def _graceful(signum: int, frame: object) -> None:
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        # ValueError/OSError here means we are not in the main thread, in which case
        # uvicorn's own handling applies.
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, _graceful)

    try:
        # Keep the socket that was checked above open through uvicorn startup.  A
        # check-then-close-then-bind sequence leaves a small but real window in which
        # another process can claim the fixed port (or an ephemeral port can change).
        # Passing the already-bound socket makes the reservation atomic.
        server.run(sockets=[listen_socket])
    finally:
        with contextlib.suppress(OSError):
            listen_socket.close()
        clear_handshake(expected_pid=os.getpid(), expected_token=token)
