"""The plugin's hot-path forwarder (`adapters/claude_code/forward.py`).

It runs once per tool call as ``python -I -S forward.py``: standalone, builtin modules
only. These tests hold it to the three things it exists for: being correct about the
daemon's answer, never granting a permission even if the daemon (or an impostor on its
port) says to, and failing open — exit 0, no output — on every kind of failure.
"""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from agentguard.adapters.claude_code import forward
from tests.conftest import free_port, pre_tool_use, user_prompt_submit

FORWARD = Path(forward.__file__)


def run_forward(
    home: Path, payload: dict | bytes, timeout: str = "4", **env_extra
) -> subprocess.CompletedProcess:
    """Exactly how the plugin runs it: a file, isolated, no site."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENTGUARD_", "CLAUDE_PLUGIN_"))}
    env.update(AGENTGUARD_HOME=str(home), **env_extra)
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return subprocess.run(
        [sys.executable, "-I", "-S", str(FORWARD), "--timeout", timeout],
        input=body,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )


def handshake(home: Path, port: int, token: str = "tok", host: str = "127.0.0.1") -> None:
    (home / "daemon.json").write_text(json.dumps({"host": host, "port": port, "token": token, "pid": 1}))


class Responder(BaseHTTPRequestHandler):
    """A stand-in daemon whose answer each test chooses."""

    status = 200
    body = b"{}"
    chunked = False
    seen: ClassVar[list] = []

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        type(self).seen.append((self.path, dict(self.headers), self.rfile.read(length)))
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        if self.chunked:
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            half = len(self.body) // 2
            for part in (self.body[:half], self.body[half:]):
                self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_daemon(isolated_home):
    class Handler(Responder):
        seen: ClassVar[list] = []

    server = HTTPServer(("127.0.0.1", 0), Handler)
    Handler.protocol_version = "HTTP/1.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    handshake(isolated_home, server.server_address[1])
    yield Handler
    server.shutdown()
    server.server_close()


class TestScanner:
    @pytest.mark.parametrize(
        "text",
        ['{"a": 1, "b": [true, false, null], "c": "é\\n"}', "  {}  ", "[1, 2.5, -3e2]", '"s"'],
    )
    def test_matches_the_stdlib_parser(self, text):
        assert forward.loads(text) == json.loads(text)

    @pytest.mark.parametrize("text", ["", "{", '{"a": 1} trailing', "nope"])
    def test_rejects_what_the_stdlib_rejects(self, text):
        with pytest.raises(ValueError):
            forward.loads(text)

    def test_a_changed_private_scanner_falls_back_to_json(self, monkeypatch):
        """CPython 3.15 added a field the private scanner reads; uv installs the newest
        CPython where none is present, and the runtime must still work there."""
        import _json
        import importlib

        def refuse(context):
            raise AttributeError("'_Ctx' object has no attribute 'something_new'")

        monkeypatch.setattr(_json, "make_scanner", refuse)
        fallback = importlib.reload(forward)
        try:
            assert fallback._scan is None
            assert fallback.loads('{"a": [1, true]}') == {"a": [1, True]}
            with pytest.raises(ValueError):
                fallback.loads("{")
        finally:
            monkeypatch.undo()
            importlib.reload(forward)

    def test_imports_nothing_slow(self):
        """`json` pulls in `re` (~7 ms) and `socket` pulls in `enum` (~2 ms)."""
        probe = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                f"import runpy, sys; sys.argv=['x', '--help']; "
                f"import importlib.util as u; s=u.spec_from_file_location('fwd', {str(FORWARD)!r}); "
                f"m=u.module_from_spec(s); s.loader.exec_module(m); "
                f"print(sorted(n for n in ('json', 're', 'socket', 'enum', 'http') if n in sys.modules))",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert probe.stdout.strip() == "[]"


class TestEndpoint:
    @pytest.mark.parametrize("host", ["127.0.0.1", "127.1.2.3", "localhost", " 127.0.0.1 "])
    def test_loopback_accepted(self, host):
        assert forward.endpoint_of({"host": host, "port": 9, "token": "t"}) is not None

    @pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.1", "::1", "evil.example", "127.0.0.256", 7])
    def test_anything_else_refused(self, host):
        """The bearer token never leaves the loopback interface."""
        assert forward.endpoint_of({"host": host, "port": 9, "token": "t"}) is None

    @pytest.mark.parametrize("token", ["", "a b", "a\r\nX-Evil: 1", None, "tök"])
    def test_tokens_that_could_inject_headers_are_refused(self, token):
        assert forward.endpoint_of({"host": "127.0.0.1", "port": 9, "token": token}) is None

    @pytest.mark.parametrize("port", [0, 70000, "8787", None, True])
    def test_bad_ports_refused(self, port):
        assert forward.endpoint_of({"host": "127.0.0.1", "port": port, "token": "t"}) is None


class TestForwarding:
    def test_relays_the_daemons_decision(self, fake_daemon, isolated_home):
        decision = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}}
        fake_daemon.body = json.dumps(decision).encode()
        result = run_forward(isolated_home, pre_tool_use())
        assert result.returncode == 0
        assert json.loads(result.stdout) == decision
        path, headers, body = fake_daemon.seen[0]
        assert path == "/hook/claude-code"
        assert headers["Authorization"] == "Bearer tok"
        assert json.loads(body)["hook_event_name"] == "PreToolUse"

    def test_chunked_responses_are_decoded(self, fake_daemon, isolated_home):
        decision = {"decision": "block", "reason": "run the tests"}
        fake_daemon.body = json.dumps(decision).encode()
        fake_daemon.chunked = True
        result = run_forward(isolated_home, pre_tool_use())
        assert json.loads(result.stdout) == decision

    def test_no_opinion_prints_nothing(self, fake_daemon, isolated_home):
        fake_daemon.body = b"{}"
        result = run_forward(isolated_home, pre_tool_use())
        assert result.returncode == 0 and result.stdout == b""

    @pytest.mark.parametrize(
        "body",
        [
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}},
            {"hookSpecificOutput": {"decision": {"behavior": "allow"}}},
            {"decision": "approve"},
        ],
    )
    def test_never_relays_a_grant(self, fake_daemon, isolated_home, body):
        """Even if the thing on the daemon's port says "allow", the agent hears nothing."""
        fake_daemon.body = json.dumps(body).encode()
        result = run_forward(isolated_home, pre_tool_use())
        assert result.returncode == 0 and result.stdout == b""

    @pytest.mark.parametrize(
        ("status", "body"), [(500, b"{}"), (401, b"{}"), (200, b"<html>"), (200, b"[1]")]
    )
    def test_bad_answers_fail_open(self, fake_daemon, isolated_home, status, body):
        fake_daemon.status = status
        fake_daemon.body = body
        result = run_forward(isolated_home, pre_tool_use())
        assert result.returncode == 0 and result.stdout == b""


class TestFailOpen:
    def test_no_handshake(self, isolated_home):
        result = run_forward(isolated_home, pre_tool_use())
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")

    def test_nothing_listening(self, isolated_home):
        handshake(isolated_home, free_port())
        result = run_forward(isolated_home, pre_tool_use())
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")

    def test_a_wedged_daemon_is_given_up_on(self, isolated_home):
        """Accepts the connection, never answers: the forwarder's own timeout ends it."""
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        handshake(isolated_home, listener.getsockname()[1])
        try:
            result = run_forward(isolated_home, pre_tool_use(), timeout="0.5")
        finally:
            listener.close()
        assert (result.returncode, result.stdout) == (0, b"")

    def test_symlinked_handshake_is_refused(self, isolated_home, tmp_path):
        real = tmp_path / "elsewhere.json"
        real.write_text(json.dumps({"host": "127.0.0.1", "port": 1, "token": "t", "pid": 1}))
        (isolated_home / "daemon.json").symlink_to(real)
        assert forward.read_handshake(str(isolated_home)) is None

    @pytest.mark.parametrize("payload", [b"", b"   ", b"x" * (forward.MAX_STDIN_BYTES + 1)])
    def test_empty_or_oversized_input(self, fake_daemon, isolated_home, payload):
        result = run_forward(isolated_home, payload)
        assert (result.returncode, result.stdout) == (0, b"")
        assert fake_daemon.seen == []

    def test_disabled_session_sends_nothing(self, fake_daemon, isolated_home):
        result = run_forward(isolated_home, pre_tool_use(), AGENTGUARD_DISABLE="1")
        assert (result.returncode, result.stdout) == (0, b"")
        assert fake_daemon.seen == []


class TestStandDown:
    def test_markers_silence_the_plugin(self, fake_daemon, isolated_home, tmp_path):
        data = tmp_path / "plugin-data"
        project = tmp_path / "project"
        (data / "standdown").mkdir(parents=True)
        (data / "standdown" / forward.project_key(str(project))).write_text("[]")
        result = run_forward(
            isolated_home,
            pre_tool_use(),
            CLAUDE_PLUGIN_DATA=str(data),
            CLAUDE_PROJECT_DIR=str(project),
        )
        assert (result.returncode, result.stdout) == (0, b"")
        assert fake_daemon.seen == [], "nothing is sent while settings hooks cover the project"

    def test_a_user_scope_marker_covers_every_project(self, monkeypatch, tmp_path):
        data = tmp_path / "plugin-data"
        (data / "standdown").mkdir(parents=True)
        (data / "standdown" / "user").write_text("[]")
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "anything"))
        assert forward.standing_down()

    def test_no_markers_no_stand_down(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert not forward.standing_down()

    def test_project_keys_are_filenames(self):
        key = forward.project_key("/Users/me/My Project/x" * 20)
        assert "/" not in key and len(key) <= 220


class TestAgainstARealDaemon:
    def test_a_real_round_trip(self, daemon, workspace):
        """The whole path: a real daemon, a real decision, the real forwarder."""
        run_forward(daemon.home, {**user_prompt_submit("push it", cwd=str(workspace))})
        result = run_forward(
            daemon.home, pre_tool_use("Bash", cwd=str(workspace), command="git push --force origin main")
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)["hookSpecificOutput"]
        assert out["permissionDecision"] == "ask"
        assert "force push" in out["permissionDecisionReason"]


def test_run_is_total(monkeypatch):
    """`run()` itself never raises, whatever it is handed."""
    monkeypatch.setenv("AGENTGUARD_HOME", "/nonexistent/agentguard-home")
    out = io.BytesIO()
    assert forward.run([], io.BytesIO(b'{"hook_event_name": "Stop"}'), out) == 0
    assert forward.run(["--timeout", "x"], io.BytesIO(b"\xff\xfe"), out) == 0
    assert out.getvalue() == b""
