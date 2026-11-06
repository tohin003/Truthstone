"""The Codex plugin's lean forwarder (WP9): ``python -I -S forward.py``, stdlib builtins only.

It must answer exactly as the runtime's hot path does, resolve the home by the rule every
entry point shares, never import the package (it is not importable under ``-S``), never let a
repository file shadow a module, never grant, and fail open on everything.
"""

from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from truthstone import names
from truthstone.adapters.codex import forward
from truthstone.daemon import private_paths

FORWARD = Path(forward.__file__)


class _Daemon:
    """A loopback stand-in for the daemon: records requests, answers with ``reply``."""

    def __init__(self, reply: bytes = b"{}", status: int = 200) -> None:
        self.requests: list[tuple[str, dict, bytes]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append((self.path, dict(self.headers), body))
                self.send_response(status)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def daemon(isolated_home: Path):
    servers: list[_Daemon] = []

    def start(reply: dict | bytes = b"{}", status: int = 200, pid: int | None = None) -> _Daemon:
        body = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
        server = _Daemon(body, status)
        servers.append(server)
        handshake = {"host": "127.0.0.1", "port": server.port, "token": "tok", "pid": pid or os.getpid()}
        (isolated_home / "daemon.json").write_text(json.dumps(handshake))
        return server

    yield start
    for server in servers:
        server.close()


def _run(payload: dict | bytes, *argv: str) -> bytes:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    out = io.BytesIO()
    assert forward.run(list(argv), io.BytesIO(body), out) == 0
    return out.getvalue()


PRE = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/w", "tool_name": "Bash"}


def test_it_forwards_the_payload_to_the_codex_route_and_prints_the_answer(daemon):
    deny = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "no",
        }
    }
    server = daemon(deny)
    assert json.loads(_run(PRE)) == deny
    path, headers, body = server.requests[0]
    assert path == "/hook/codex" and headers["Authorization"] == "Bearer tok" and json.loads(body) == PRE


@pytest.mark.parametrize(
    "reply, status",
    [
        ({"hookSpecificOutput": {"permissionDecision": "allow"}}, 200),  # never a grant
        ({"decision": "approve"}, 200),
        (b"not json", 200),
        ({"decision": "block", "reason": "x"}, 500),
        ({}, 200),
    ],
)
def test_it_prints_nothing_for_grants_garbage_errors_and_no_opinion(daemon, reply, status):
    daemon(reply, status)
    assert _run(PRE) == b""


def test_it_fails_open_without_a_live_daemon(isolated_home: Path, daemon):
    assert _run(PRE) == b""  # no handshake at all
    daemon(pid=2**22 + 12345)  # a PID that is not running: skipped, nothing sent
    assert _run(PRE) == b""
    (isolated_home / "daemon.json").write_text('{"host": "10.0.0.1", "port": 1, "token": "t", "pid": 1}')
    assert _run(PRE) == b""  # never anywhere but loopback


def test_switched_off_means_nothing_is_sent(daemon, monkeypatch):
    server = daemon({"decision": "block", "reason": "x"})
    monkeypatch.setenv("TRUTHSTONE_DISABLE", "1")
    assert _run(PRE) == b"" and not server.requests


def test_a_symlinked_handshake_is_refused(isolated_home: Path, daemon, tmp_path):
    daemon({"decision": "block", "reason": "x"})
    real = tmp_path / "elsewhere.json"
    (isolated_home / "daemon.json").rename(real)
    (isolated_home / "daemon.json").symlink_to(real)
    assert _run(PRE) == b""


def test_the_home_is_resolved_by_the_shared_rule(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    for home in (str(plain), str(tmp_path / "missing"), "relative/home"):
        assert forward.resolve_home(home) == private_paths.resolve_home(home)
    link = tmp_path / "link"
    link.symlink_to(plain)
    assert forward.resolve_home(str(link)) == private_paths.resolve_home(str(link))
    monkeypatch.setenv("TRUTHSTONE_HOME", str(link))
    assert forward.configured_home() == private_paths.configured_home()


def test_former_names_match_the_registry():
    assert forward.FORMER == names.FORMER


def test_it_imports_builtins_and_the_standard_library_only():
    tree = ast.parse(FORWARD.read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
    }
    assert imported <= {"__future__", "_json", "_socket", "os", "stat", "sys", "json"}


def test_as_launched_it_runs_isolated_and_a_repository_module_cannot_shadow_one(daemon, tmp_path):
    """``python -I -S forward.py`` inside a repository holding a hostile ``_json.py``/``os.py``."""
    deny = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "no",
        }
    }
    daemon(deny)
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("_json.py", "stat.py", "json.py"):
        (repo / name).write_text("raise SystemExit('shadowed')\n")
    env = {k: v for k, v in os.environ.items() if k.startswith(("TRUTHSTONE", "HOME", "PATH"))}
    env["PYTHONPATH"] = str(repo)  # ignored under -I
    proc = subprocess.run(
        [sys.executable, "-I", "-S", str(FORWARD), "--timeout", "4"],
        input=json.dumps(PRE).encode(),
        cwd=repo,
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0 and json.loads(proc.stdout) == deny, proc.stderr


# -- the runtime's side ------------------------------------------------------------------------


def test_session_start_installs_the_forwarder_and_its_python_for_the_launcher(tmp_path, monkeypatch):
    from truthstone.adapters.codex import hook, native

    data = tmp_path / "plugin-data"
    builds: list[str] = []
    monkeypatch.setattr(native, "start", lambda lean, python=None: builds.append(lean))
    monkeypatch.setenv("PLUGIN_DATA", str(data))
    monkeypatch.setattr(hook, "_lifecycle", lambda: (None, hook.UNGUARDED_NOTICE, None))
    start = {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(tmp_path), "source": "startup"}
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(start).encode())))
    assert hook.main(["session-start"]) == 0
    lean = data / hook.LEAN_DIR
    assert (lean / "forward.py").read_bytes() == FORWARD.read_bytes()
    assert (lean / "python").read_text() == sys.executable + "\n"
    assert str(lean) in (lean / "run.py").read_text()
    assert builds == [str(lean)]  # and the native forwarder's build starts (test_codex_native.py)
    assert not hook.install_lean("relative/data")  # only an absolute data directory


def test_the_installed_runner_forwards_isolated_from_its_cached_module(tmp_path, daemon, monkeypatch):
    from truthstone.adapters.codex import hook, native

    monkeypatch.setattr(native, "start", lambda lean, python=None: None)  # the Python path only
    deny = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}}
    daemon(deny)
    assert hook.install_lean(str(tmp_path / "data"))
    lean = tmp_path / "data" / hook.LEAN_DIR
    env = {k: v for k, v in os.environ.items() if k.startswith(("TRUTHSTONE", "HOME", "PATH"))}
    for _ in range(2):  # the second run imports the forwarder from its cached bytecode
        proc = subprocess.run(
            [sys.executable, "-I", "-S", str(lean / "run.py"), "--timeout", "4"],
            input=json.dumps(PRE).encode(),
            cwd=tmp_path,
            capture_output=True,
            env=env,
            timeout=60,
        )
        assert proc.returncode == 0 and json.loads(proc.stdout) == deny, proc.stderr
    assert list((lean / "__pycache__").glob("forward.*.pyc"))


def test_the_runtime_hot_path_imports_only_the_forwarder(tmp_path):
    """``truthstone-codex-hook pre-tool-use``: no json, socket, re or enum (WP9's import diet)."""
    src = Path(forward.__file__).parents[3]
    probe = (
        "import io, sys\n"
        f"sys.path.insert(0, {str(src)!r})\n"
        "from truthstone.adapters.codex import hook\n"
        "sys.stdin = io.TextIOWrapper(io.BytesIO(b'{}'))\n"
        "hook.main(['pre-tool-use'])\n"
        "print(sorted(m for m in ('json', 'socket', 're', 'enum', 'truthstone.names') if m in sys.modules))\n"
    )
    env = {"PATH": "/usr/bin:/bin", "TRUTHSTONE_HOME": str(tmp_path / "home")}
    proc = subprocess.run([sys.executable, "-I", "-S", "-c", probe], capture_output=True, text=True, env=env)
    assert proc.returncode == 0 and proc.stdout.strip() == "[]", proc.stderr
