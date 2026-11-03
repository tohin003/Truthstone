"""The Claude Code plugin: package, launcher, entry points, and a whole session.

The plugin is distributed through the repository's own marketplace and must work with no
manual settings editing. These tests check the package Claude Code reads (manifest, hooks,
skills, marketplace), then drive `hooks/hooks.json` the way Claude Code does
(`tests/plugin_harness.py`) against a real daemon.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from agentguard.adapters.claude_code import forward, install, plugin, settings_scan, translate
from tests import plugin_harness as harness
from tests.conftest import free_port

SKILLS = harness.PLUGIN_ROOT / "skills"


def frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, f"{path} has no front matter"
    return yaml.safe_load(match.group(1)), match.group(2)


# -- the package ---------------------------------------------------------------------------


class TestManifest:
    def test_identity(self):
        manifest = json.loads(harness.MANIFEST.read_text())
        assert manifest["name"] == settings_scan.PLUGIN_NAME
        assert manifest["license"] == "Apache-2.0"
        # A plain release version: it names the runtime's git tag (v<version>), and the
        # community scanner rejects pre-release tags.
        assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
        for key in ("hooks", "skills", "commands", "mcpServers"):
            assert key not in manifest, f"{key}: use the default location, never declare it twice"

    def test_ships_its_license_and_security_policy(self):
        assert (harness.PLUGIN_ROOT / "LICENSE").read_text() == (harness.REPO_ROOT / "LICENSE").read_text()
        assert (harness.PLUGIN_ROOT / "SECURITY.md").exists()

    def test_no_codex_manifest_and_no_bin(self):
        """Claude-only. `bin/` would also stop claude.ai and Cowork installing it."""
        assert not (harness.PLUGIN_ROOT / ".codex-plugin").exists()
        assert not (harness.PLUGIN_ROOT / "bin").exists()


class TestMarketplace:
    def test_lists_the_plugin_under_the_manifest_name(self):
        market = json.loads(harness.MARKETPLACE.read_text())
        assert market["name"] == "agentguard"
        assert market["owner"]["name"]
        entry = next(p for p in market["plugins"] if p["name"] == settings_scan.PLUGIN_NAME)
        assert (harness.REPO_ROOT / entry["source"]).resolve() == harness.PLUGIN_ROOT.resolve()
        assert "version" not in entry, "plugin.json is the one place the version lives"

    def test_every_listed_plugin_is_a_claude_plugin_without_codex_hooks_leaking_in(self):
        """Claude Code loads a manifest-less directory's hooks/ and skills/ too, so the
        Codex plugin must never be listed here."""
        market = json.loads(harness.MARKETPLACE.read_text())
        for entry in market["plugins"]:
            root = (harness.REPO_ROOT / entry["source"]).resolve()
            assert root.is_relative_to(harness.REPO_ROOT / "plugins")
            assert (root / ".claude-plugin" / "plugin.json").exists(), entry["name"]
            manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
            assert manifest["name"] == entry["name"]
        assert "./plugins/agentguard" not in [entry["source"] for entry in market["plugins"]]


class TestHooksConfig:
    def test_subscribes_what_the_adapter_translates(self):
        hooks = harness.load_hooks()
        assert set(hooks) <= set(translate.EVENT_MAP)
        expected = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                    "PostToolUseFailure", "Stop", "SessionEnd"}
        assert set(hooks) == expected

    def test_matchers_are_the_installers(self):
        """One definition of which tools AgentGuard sees, for both install paths."""
        hooks = harness.load_hooks()
        assert hooks["PreToolUse"][0]["matcher"] == install.MUTATING_MATCHER
        assert hooks["PostToolUse"][0]["matcher"] == install.MUTATING_MATCHER
        assert hooks["PostToolUseFailure"][0]["matcher"] == install.FAILURE_MATCHER

    def test_only_shell_form_command_hooks(self):
        """`http` cannot authenticate from a plugin (no per-user secret reaches its
        headers). Exec form (`args`) is avoided: on a Claude Code that ignored `args`,
        `"command": "sh"` would run the hook's JSON payload as a shell script."""
        for groups in harness.load_hooks().values():
            for group in groups:
                for hook in group["hooks"]:
                    assert hook["type"] == "command"
                    assert "args" not in hook
                    assert 0 < hook["timeout"] <= 300

    def test_placeholders_are_quoted(self):
        for groups in harness.load_hooks().values():
            for group in groups:
                for hook in group["hooks"]:
                    for var in re.findall(r"\$\{CLAUDE_PLUGIN_\w+\}[^\s;]*", hook["command"]):
                        assert f'"{var}' in hook["command"] or var.endswith('"'), hook["command"]

    def test_per_tool_hooks_exec_the_forwarder_and_give_up_before_claude_does(self):
        hooks = harness.load_hooks()
        for event in ("PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop", "SessionEnd"):
            hook = hooks[event][0]["hooks"][0]
            assert '[ -x "$p" ] || exit 0' in hook["command"], "no runtime yet: stay silent"
            assert "-I -S" in hook["command"]
            assert "forward.py" in hook["command"]
            budget = float(re.search(r"--timeout (\S+)", hook["command"]).group(1))
            assert budget < hook["timeout"], event
        # Claude Code gives SessionEnd hooks 1.5 s in total, and a plugin cannot raise it.
        end = hooks["SessionEnd"][0]["hooks"][0]
        assert float(re.search(r"--timeout (\S+)", end["command"]).group(1)) < 1.5

    def test_hooks_never_name_the_product_version(self):
        """Upgrades change plugin.json's version, never hooks.json."""
        text = harness.HOOKS_FILE.read_text()
        assert json.loads(harness.MANIFEST.read_text())["version"] not in text


class TestSkills:
    def test_every_skill_has_a_name_and_description(self):
        names = set()
        for path in sorted(SKILLS.glob("*/SKILL.md")):
            meta, _ = frontmatter(path)
            assert isinstance(meta.get("name"), str) and meta["name"], path
            assert meta.get("description"), path
            names.add(meta["name"])
        assert names == {"agentguard", "doctor", "log", "why", "report", "on", "off"}

    def test_the_guidance_skill_is_for_claude(self):
        meta, body = frontmatter(SKILLS / "agentguard" / "SKILL.md")
        assert meta.get("user-invocable") is False
        assert not meta.get("disable-model-invocation")
        assert "completion gate" in body and "never" in body.lower()

    @pytest.mark.parametrize("name", ["doctor", "log", "why", "report", "on", "off"])
    def test_commands_are_user_invoked_and_pre_approved(self, name):
        meta, _ = frontmatter(SKILLS / name / "SKILL.md")
        assert meta["disable-model-invocation"] is True
        assert meta["allowed-tools"] == 'Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" *)'

    @pytest.mark.parametrize("name", ["doctor", "log", "why", "report", "on", "off"])
    def test_user_arguments_never_reach_an_injected_command(self, name):
        """`$ARGUMENTS` is substituted as typed, unescaped: inside a !`…` command it
        would be shell injection."""
        _, body = frontmatter(SKILLS / name / "SKILL.md")
        for command in re.findall(r"!`([^`]*)`", body):
            assert "$ARGUMENTS" not in command and not re.search(r"\$\d", command)
            assert command.startswith('sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" ')


# -- the launcher --------------------------------------------------------------------------


@pytest.fixture
def plugin_dirs(tmp_path, isolated_home):
    data = tmp_path / "plugin-data"
    project = tmp_path / "project"
    project.mkdir()
    yield data, project, isolated_home
    stop_daemon(isolated_home)


def stop_daemon(home: Path) -> None:
    try:
        pid = json.loads((home / "daemon.json").read_text())["pid"]
        os.kill(int(pid), signal.SIGTERM)
    except (OSError, ValueError, KeyError, TypeError):
        pass


def fake_runtime(data: Path, spec: str = "test-runtime") -> str:
    """The data-directory layout `hook.sh` maintains, pointing at this test's venv."""
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs to run inside a virtualenv")
    data.mkdir(parents=True, exist_ok=True)
    (data / "runtime").symlink_to(Path(sys.prefix))
    (data / "forward.py").symlink_to(forward.__file__)
    (data / "runtime.ready").write_text(spec + "\n")
    return spec


def launcher(kind: str, env: dict, payload: dict | None = None, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", str(harness.HOOK_SCRIPT), kind, *args],
        input=json.dumps(payload or {}).encode(),
        capture_output=True,
        env=env,
        cwd=env["CLAUDE_PROJECT_DIR"],
        timeout=240,
        check=False,
    )


def session_payload(project: Path, session: str = "s-1") -> dict:
    return {
        "session_id": session,
        "cwd": str(project),
        "hook_event_name": "SessionStart",
        "source": "startup",
    }


class TestLauncher:
    def test_without_uv_it_says_how_to_install_and_nothing_else(self, plugin_dirs):
        data, project, home = plugin_dirs
        env = harness.plugin_env(data, project, home, AGENTGUARD_UV="/nonexistent/uv")
        result = launcher("session-start", env, session_payload(project))
        assert result.returncode == 0
        message = json.loads(result.stdout)["systemMessage"]
        assert "uv" in message and "astral.sh/uv/install.sh" in message
        assert "unguarded" in message
        assert not (data / "runtime.ready").exists()

    def test_disabled_says_nothing(self, plugin_dirs):
        data, project, home = plugin_dirs
        env = harness.plugin_env(
            data, project, home, AGENTGUARD_UV="/nonexistent/uv", AGENTGUARD_DISABLE="1"
        )
        result = launcher("session-start", env, session_payload(project))
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")

    def test_the_runtime_source_follows_the_plugin_version(self, plugin_dirs, tmp_path):
        """No separate pin to edit: v<plugin version> from GitHub."""
        data, project, home = plugin_dirs
        record = tmp_path / "uv-args"
        fake_uv = tmp_path / "uv"
        fake_uv.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{record}"\nexit 1\n')
        fake_uv.chmod(0o755)
        env = harness.plugin_env(data, project, home, AGENTGUARD_UV=str(fake_uv))
        result = launcher("session-start", env, session_payload(project))
        assert result.returncode == 0
        message = json.loads(result.stdout)["systemMessage"]
        version = json.loads(harness.MANIFEST.read_text())["version"]
        assert f"git+https://github.com/tohin003/AgentGuard@v{version}" in message
        assert str(data / "install.log") in message
        assert "venv" in record.read_text()
        assert not (data / "install.lock").exists(), "the lock is released on failure"

    def test_a_stale_install_lock_expires(self, plugin_dirs, tmp_path):
        data, project, home = plugin_dirs
        lock = data / "install.lock"
        lock.mkdir(parents=True)
        old = time.time() - 3600
        os.utime(lock, (old, old))
        env = harness.plugin_env(data, project, home, AGENTGUARD_UV=str(tmp_path / "missing-uv"))
        # No uv: it never gets as far as the lock, so give it a uv that fails fast.
        fake_uv = tmp_path / "uv"
        fake_uv.write_text("#!/bin/sh\nexit 1\n")
        fake_uv.chmod(0o755)
        env["AGENTGUARD_UV"] = str(fake_uv)
        env["AGENTGUARD_INSTALL_WAIT"] = "2"
        result = launcher("session-start", env, session_payload(project))
        assert "could not install" in json.loads(result.stdout)["systemMessage"]
        assert not lock.exists()

    def test_per_tool_hooks_are_silent_before_the_runtime_exists(self, plugin_dirs):
        data, project, home = plugin_dirs
        env = harness.plugin_env(data, project, home)
        payload = {"session_id": "s", "cwd": str(project), "tool_name": "Bash",
                   "tool_input": {"command": "git push --force"}}
        for run in harness.run_event("PreToolUse", payload, env):
            assert (run.returncode, run.stdout, run.stderr) == (0, "", "")

    def test_commands_explain_a_missing_runtime(self, plugin_dirs):
        data, project, home = plugin_dirs
        env = harness.plugin_env(data, project, home, AGENTGUARD_UV="/nonexistent/uv")
        result = launcher("cli", env, None, str(data), "doctor")
        assert result.returncode == 0
        assert b"not installed yet" in result.stdout
        assert b"astral.sh/uv/install.sh" in result.stdout


# -- the plugin entry points ---------------------------------------------------------------


class TestStandDown:
    def test_settings_hooks_make_the_plugin_stand_by(self, plugin_dirs, monkeypatch, tmp_path):
        data, project, home = plugin_dirs
        config = tmp_path / "claude-config"
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        install.install(config / "settings.json")

        out = plugin.session_start(session_payload(project))
        assert "standing by" in out["systemMessage"]
        assert "agentguard uninstall claude --global" in out["systemMessage"]
        assert forward.standing_down()
        assert not (home / "daemon.json").exists(), "the settings hooks start their own daemon"
        assert plugin.prompt({"session_id": "s-1", "cwd": str(project)}) == {}

        install.uninstall(config / "settings.json")
        plugin.stand_down(session_payload(project))
        assert not forward.standing_down(), "the next session takes over"

    def test_project_hooks_stand_the_plugin_down_only_there(self, plugin_dirs, monkeypatch, tmp_path):
        data, project, _ = plugin_dirs
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
        install.install(project / ".claude" / "settings.local.json")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        found = plugin.stand_down(session_payload(project))
        assert [scope for scope, _ in found] == ["local"]
        assert forward.standing_down()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert not forward.standing_down()


class TestUnguarded:
    def test_a_daemon_that_cannot_start_is_reported_once(self, plugin_dirs, monkeypatch):
        data, project, home = plugin_dirs
        (home / "config.toml").write_text("[daemon]\nport = 1\n")  # unbindable
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(data / "no-config"))
        monkeypatch.setenv("AGENTGUARD_START_TIMEOUT", "1")
        first = plugin.prompt({"session_id": "s-u", "cwd": str(project)})
        second = plugin.prompt({"session_id": "s-u", "cwd": str(project)})
        assert "UNGUARDED" in first["systemMessage"]
        assert "/agentguard:doctor" in first["systemMessage"]
        assert second == {}


# -- whole sessions ------------------------------------------------------------------------


@pytest.fixture
def guarded_project(plugin_dirs):
    data, project, home = plugin_dirs
    (home / "config.toml").write_text(f"[daemon]\nport = {free_port()}\n")
    (project / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (project / "tests").mkdir()
    (project / "tests" / "test_app.py").write_text(
        "from app import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    spec = fake_runtime(data)
    env = harness.plugin_env(
        data,
        project,
        home,
        AGENTGUARD_RUNTIME_SPEC=spec,
        CLAUDE_CONFIG_DIR=str(data.parent / "claude-config"),
    )
    return data, project, home, env


def one(runs: list[harness.HookRun]) -> dict:
    assert len(runs) == 1, runs
    run = runs[0]
    assert run.returncode == 0, run.stderr
    return run.output


class TestWholeSession:
    def test_a_session_through_hooks_json(self, guarded_project):
        """SessionStart starts the daemon; risky commands are sent for review; a plain
        edit is silent; a failing run (PostToolUseFailure) holds the completion gate; when
        the gate gives up, the developer is told; SessionEnd is quiet."""
        _, project, home, env = guarded_project
        base = {"session_id": "whole-1", "cwd": str(project), "permission_mode": "default"}

        def hook(event: str, **fields) -> dict:
            return one(harness.run_event(event, {**base, **fields}, env))

        assert hook("SessionStart", source="startup") == {}
        assert json.loads((home / "daemon.json").read_text())["port"]

        prompt = hook("UserPromptSubmit", prompt="Make add() return an int")
        assert "[AgentGuard]" in prompt["hookSpecificOutput"]["additionalContext"]

        push = {"command": "git push --force origin main"}
        review = hook("PreToolUse", tool_name="Bash", tool_input=push)["hookSpecificOutput"]
        assert review["permissionDecision"] == "ask"

        path = str(project / "app.py")
        edit = {"file_path": path, "old_string": "a + b", "new_string": "int(a + b)"}
        assert hook("PreToolUse", tool_name="Edit", tool_input=edit) == {}
        (project / "app.py").write_text("def add(a, b):\n    return int(a + b)\n")
        response = {"filePath": path}
        assert hook("PostToolUse", tool_name="Edit", tool_input=edit, tool_response=response) == {}

        failing = hook(
            "PostToolUseFailure",
            tool_name="Bash",
            tool_input={"command": "pytest -q"},
            error="Exit code 1\nF\n1 failed in 0.02s",
            is_interrupt=False,
        )
        assert failing == {}

        held = hook("Stop", stop_hook_active=False, last_assistant_message="Done, tests pass.")
        assert held["decision"] == "block"
        assert "verification_failed" in held["reason"]

        gave_up = hook("Stop", stop_hook_active=True, last_assistant_message="Done.")
        assert "unverified" in gave_up["systemMessage"]

        assert hook("SessionEnd", reason="other") == {}

    def test_per_tool_hooks_are_fast(self, guarded_project):
        """The plugin's hot path: one shell plus a Python with no site and no imports."""
        _, project, _, env = guarded_project
        base = {"session_id": "fast-1", "cwd": str(project)}
        one(harness.run_event("SessionStart", {**base, "source": "startup"}, env))
        payload = {**base, "tool_name": "Bash", "tool_input": {"command": "ls"}}
        times = sorted(
            run.ms for _ in range(20) for run in harness.run_event("PreToolUse", payload, env)
        )
        assert times[len(times) // 2] < 150, times  # generous: CI machines vary; measured ~18 ms

    def test_commands_run_the_runtime(self, guarded_project):
        data, project, _, env = guarded_project
        start = {"session_id": "c-1", "cwd": str(project), "source": "startup"}
        one(harness.run_event("SessionStart", start, env))
        status = launcher("plugin", env, None, str(data), "status")
        assert b"daemon       pid" in status.stdout
        assert b"guarded by the plugin" in status.stdout
        log = launcher("cli", env, None, str(data), "log", "-n", "5")
        assert log.returncode == 0


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv")
class TestRealBootstrap:
    def test_installs_the_runtime_with_uv_then_upgrades_it(self, plugin_dirs):
        """The real thing: uv builds a virtualenv in the plugin's data directory from a
        local checkout, the per-tool hooks start working, and a new source upgrades it
        and restarts the daemon onto the new code."""
        data, project, home = plugin_dirs
        (home / "config.toml").write_text(f"[daemon]\nport = {free_port()}\n")
        env = harness.plugin_env(
            data, project, home,
            AGENTGUARD_RUNTIME_SPEC=str(harness.REPO_ROOT),
            CLAUDE_CONFIG_DIR=str(data.parent / "claude-config"),
        )
        first = launcher("session-start", env, session_payload(project))
        assert first.returncode == 0, first.stderr
        assert (data / "runtime.ready").read_text().strip() == str(harness.REPO_ROOT)
        assert (data / "runtime" / "bin" / "python").exists()
        assert Path(os.path.realpath(data / "forward.py")) == Path(forward.__file__).resolve()
        pid = json.loads((home / "daemon.json").read_text())["pid"]

        # A different source (a plugin upgrade): reinstall, then restart the daemon.
        env["AGENTGUARD_RUNTIME_SPEC"] = str(harness.REPO_ROOT) + "/"
        upgraded = launcher("session-start", env, session_payload(project, "s-2"))
        assert upgraded.returncode == 0, upgraded.stderr
        assert json.loads((home / "daemon.json").read_text())["pid"] != pid
