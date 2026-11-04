"""The shim: spawning the daemon safely, per-session modes (R10), never-silent states (R9).

Everything here runs against a real daemon process, because each property is about what
reaches Claude Code across a process boundary: a mode the daemon cannot see, a state a
developer cannot see.
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys

from tests.conftest import REPO_ROOT, DaemonProcess, free_port, pre_tool_use, user_prompt_submit
from truthstone.adapters.claude_code import shim


def run_shim(home, flag, payload, **env_extra):
    env = dict(os.environ, TRUTHSTONE_HOME=str(home), PYTHONPATH=str(REPO_ROOT / "src"))
    env.pop("TRUTHSTONE_DISABLE", None)
    env.pop("TRUTHSTONE_OBSERVE", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "truthstone.adapters.claude_code.shim", flag],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )


def post_hook(daemon, payload):
    conn = http.client.HTTPConnection("127.0.0.1", daemon.port, timeout=10)
    try:
        conn.request(
            "POST",
            "/hook/claude-code",
            body=json.dumps(payload),
            headers={"Authorization": f"Bearer {daemon.token}", "Content-Type": "application/json"},
        )
        return json.loads(conn.getresponse().read() or b"{}")
    finally:
        conn.close()


def force_push(session_id: str, cwd: str) -> dict:
    return {
        **pre_tool_use("Bash", cwd=cwd, command="git push --force origin main"),
        "session_id": session_id,
    }


class TestDaemonSpawn:
    def test_the_daemon_never_imports_from_the_repository(self, isolated_home, monkeypatch, tmp_path):
        """The spawning hook's working directory is the developer's repository."""
        calls = []

        class FakePopen:
            def __init__(self, argv, **kwargs):
                calls.append((argv, kwargs))

        monkeypatch.setattr(subprocess, "Popen", FakePopen)
        monkeypatch.chdir(tmp_path)
        assert shim.ensure_daemon(timeout=0.2) is None
        argv, kwargs = calls[0]
        assert argv[:3] == [sys.executable, "-P", "-m"]
        assert kwargs["cwd"] == str(isolated_home)
        assert kwargs["start_new_session"] is True


class TestPerSessionModes:
    def test_a_disabled_session_is_not_judged_by_a_running_daemon(self, daemon, workspace):
        """R10: `TRUTHSTONE_DISABLE=1 claude` used to leave its http hooks guarded."""
        disabled = run_shim(
            daemon.home,
            "--health",
            {**user_prompt_submit("hi", cwd=str(workspace)), "session_id": "off-session"},
            TRUTHSTONE_DISABLE="1",
        )
        assert disabled.returncode == 0
        assert disabled.stdout == b"" and disabled.stderr == b""

        # The core opens a task on the first prompt; without one it raises nothing at all.
        for session in ("off-session", "on-session"):
            prompt = {**user_prompt_submit("push the branch", cwd=str(workspace)), "session_id": session}
            post_hook(daemon, prompt)

        assert post_hook(daemon, force_push("off-session", str(workspace))) == {}
        guarded = post_hook(daemon, force_push("on-session", str(workspace)))
        assert guarded["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_disabled_never_starts_a_daemon(self, isolated_home, workspace):
        result = run_shim(
            isolated_home,
            "--ensure-daemon",
            {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(workspace)},
            TRUTHSTONE_DISABLE="1",
        )
        assert result.returncode == 0
        assert not (isolated_home / "daemon.json").exists()

    def test_an_observed_session_is_recorded_but_hears_nothing(self, daemon, workspace):
        observed = run_shim(
            daemon.home,
            "--health",
            {**user_prompt_submit("hi", cwd=str(workspace)), "session_id": "quiet"},
            TRUTHSTONE_OBSERVE="1",
        )
        assert observed.returncode == 0
        prompt = {**user_prompt_submit("push the branch", cwd=str(workspace)), "session_id": "quiet"}
        assert post_hook(daemon, prompt) == {}, "not even the planning budget is said"
        assert post_hook(daemon, force_push("quiet", str(workspace))) == {}


class TestNeverSilent:
    def test_an_observe_only_daemon_is_reported_once_per_session(self, isolated_home, workspace):
        """R9: an observe-mode daemon started by one session silenced every session."""
        port = free_port()
        (isolated_home / "config.toml").write_text(f"observe_only = true\n[daemon]\nport = {port}\n")
        daemon = DaemonProcess(isolated_home, port)
        daemon.start()
        try:
            payload = {**user_prompt_submit("hi", cwd=str(workspace)), "session_id": "s-obs"}
            first = run_shim(isolated_home, "--health", payload)
            second = run_shim(isolated_home, "--health", payload)
        finally:
            daemon.stop()
        assert first.returncode == 0
        message = json.loads(first.stdout)["systemMessage"]
        assert "OBSERVE-ONLY" in message
        assert second.stdout == b"", "said once per session, not on every prompt"

    def test_a_switched_off_daemon_is_reported(self, isolated_home, workspace):
        port = free_port()
        (isolated_home / "config.toml").write_text(f"enabled = false\n[daemon]\nport = {port}\n")
        daemon = DaemonProcess(isolated_home, port)
        daemon.start()
        try:
            payload = {**user_prompt_submit("hi", cwd=str(workspace)), "session_id": "s-off"}
            result = run_shim(isolated_home, "--health", payload)
        finally:
            daemon.stop()
        assert "switched OFF" in json.loads(result.stdout)["systemMessage"]

    def test_degraded_reasons_are_stable_across_processes(self):
        """A reason must map to the same marker in every hook process, or it repeats."""
        body = {"degraded": ["the token in your settings is stale"]}
        first = shim.daemon_notices(body, "guard")
        second = shim.daemon_notices(dict(body), "guard")
        assert first == second and first[0][0].startswith("degraded-")

    def test_a_healthy_daemon_says_nothing(self, daemon, workspace):
        payload = {**user_prompt_submit("hi", cwd=str(workspace)), "session_id": "s-ok"}
        result = run_shim(daemon.home, "--health", payload)
        assert result.returncode == 0
        assert result.stdout == b"" and result.stderr == b""
