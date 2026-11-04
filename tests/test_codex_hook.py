"""The Codex command-hook forwarder: fail open, never exit 2, say "unguarded" once.

Codex runs it as a process on every tool call and reads exit code 2 as "block", so the
contract here is stricter than the Claude shim's: whatever happens, exit 0; an answer only
ever comes from the daemon; and a session that is not being guarded is told so once.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentguard.adapters.codex import hook

REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = Path(__file__).parent / "fixtures" / "codex_payloads"


def run(monkeypatch, capsys, payload, argv=("pre-tool-use",)) -> tuple[int, str]:
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
    code = hook.main(list(argv))
    return code, capsys.readouterr().out


def fixture(name: str, **overrides) -> dict:
    data = json.loads((PAYLOADS / f"{name}.json").read_text())
    data.update(overrides)
    return data


class TestFailOpen:
    @pytest.mark.parametrize("raw", [b"", b"not json", b"[1,2]", b"\xff\xfe", b"{" * 10])
    def test_garbage_input(self, monkeypatch, capsys, raw):
        assert run(monkeypatch, capsys, raw) == (0, "")

    def test_oversized_input(self, monkeypatch, capsys):
        raw = b'{"x": "' + b"a" * (hook.MAX_STDIN_BYTES + 10) + b'"}'
        assert run(monkeypatch, capsys, raw) == (0, "")

    def test_no_daemon_on_the_hot_path_is_silent(self, monkeypatch, capsys):
        started = time.perf_counter()
        assert run(monkeypatch, capsys, fixture("PreToolUse.Bash")) == (0, "")
        assert time.perf_counter() - started < 1.0  # no lifecycle work on a tool call

    def test_a_dead_pid_is_never_contacted(self, monkeypatch, capsys, isolated_home):
        (isolated_home / "daemon.json").write_text(
            json.dumps({"host": "127.0.0.1", "port": 9, "token": "t", "pid": 2**22 + 12345})
        )
        monkeypatch.setattr(hook, "post", lambda *a, **k: pytest.fail("contacted a dead daemon"))
        assert run(monkeypatch, capsys, fixture("PreToolUse.Bash")) == (0, "")

    def test_a_non_loopback_handshake_is_refused(self):
        assert hook._endpoint({"host": "10.0.0.5", "port": 8787}) is None
        assert hook._endpoint({"host": "127.0.0.1", "port": "8787"}) is None
        assert hook._endpoint({"host": "localhost", "port": 8787}) == ("127.0.0.1", 8787)

    def test_disabled(self, monkeypatch, capsys):
        monkeypatch.setenv("AGENTGUARD_DISABLE", "1")
        monkeypatch.setattr(hook, "_lifecycle", lambda: pytest.fail("lifecycle ran while disabled"))
        assert run(monkeypatch, capsys, fixture("SessionStart"), ("session-start",)) == (0, "")

    def test_transport_errors_are_swallowed(self, monkeypatch, capsys, isolated_home):
        (isolated_home / "daemon.json").write_text(
            json.dumps({"host": "127.0.0.1", "port": 9, "token": "t", "pid": os.getpid()})
        )

        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(hook, "post", boom)
        assert run(monkeypatch, capsys, fixture("PreToolUse.Bash")) == (0, "")


class TestUnguardedNotice:
    def test_session_start_without_a_daemon_warns_once_per_session(self, monkeypatch, capsys):
        monkeypatch.setattr(hook, "_lifecycle", lambda: (None, hook.UNGUARDED_NOTICE))
        code, out = run(monkeypatch, capsys, fixture("SessionStart"), ("session-start",))
        assert code == 0
        assert json.loads(out) == {"systemMessage": hook.UNGUARDED_NOTICE}
        assert run(monkeypatch, capsys, fixture("UserPromptSubmit"), ("user-prompt-submit",)) == (0, "")

    def test_a_daemon_without_codex_support_is_reported(self, monkeypatch, capsys, isolated_home):
        handshake = {"host": "127.0.0.1", "port": 9, "token": "t", "pid": os.getpid()}
        (isolated_home / "daemon.json").write_text(json.dumps(handshake))
        monkeypatch.setattr(hook, "_health", lambda hs: {"pid": os.getpid(), "status": "ok"})
        code, out = run(monkeypatch, capsys, fixture("SessionStart"), ("session-start",))
        assert code == 0
        assert "predates Codex support" in json.loads(out)["systemMessage"]


class TestThroughARealDaemon:
    def _invoke(self, home: Path, payload: dict, event: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, AGENTGUARD_HOME=str(home), PYTHONPATH=str(REPO_ROOT / "src"))
        env.pop("AGENTGUARD_DISABLE", None)
        return subprocess.run(
            [sys.executable, "-m", "agentguard.adapters.codex.hook", event],
            input=json.dumps(payload).encode(),
            capture_output=True,
            env=env,
            timeout=30,
            check=False,
        )

    def test_silence_and_a_challenge_end_to_end(self, daemon, isolated_home, workspace):
        cwd = str(workspace)
        session = "sess-forwarder"
        prompt = fixture("UserPromptSubmit", cwd=cwd, session_id=session, prompt="Publish the release branch")
        assert self._invoke(isolated_home, prompt, "user-prompt-submit").returncode == 0

        quiet = fixture("PreToolUse.Bash", cwd=cwd, session_id=session)
        result = self._invoke(isolated_home, quiet, "pre-tool-use")
        assert (result.returncode, result.stdout) == (0, b"")

        risky = fixture(
            "PreToolUse.Bash",
            cwd=cwd,
            session_id=session,
            tool_input={"command": "git push --force origin main"},
        )
        result = self._invoke(isolated_home, risky, "pre-tool-use")
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "force push" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_health_advertises_codex(self, daemon):
        handshake = json.loads((daemon.home / "daemon.json").read_text())
        health = hook._health(handshake)
        assert health is not None and "codex" in health["adapters"]

    def test_the_wrong_token_gets_no_decision(self, daemon, isolated_home, workspace):
        handshake = json.loads((daemon.home / "daemon.json").read_text())
        handshake["token"] = "wrong"
        payload = fixture("PreToolUse.Bash", cwd=str(workspace), tool_input={"command": "git push --force"})
        assert hook.post(handshake, json.dumps(payload).encode()) == {}
