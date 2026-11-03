"""`agentguard install codex`: idempotent, additive, exactly reversible — and honest about trust.

Writing into a developer's Codex configuration is the most invasive thing the Codex
adapter does, so these tests exist to make it boring.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentguard.adapters.codex import install as inst
from agentguard.cli.main import app

USER_HOOK = {"type": "command", "command": "python3 ~/.codex/hooks/my_policy.py", "timeout": 30}
LOOKALIKE = {"type": "command", "command": "echo agentguard.adapters.codex.hook is great", "timeout": 5}


@pytest.fixture
def codex_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


class TestHookConfig:
    def test_events_matchers_and_timeouts(self):
        config = inst.build_hook_config(python_exe="/py")
        assert set(config) == {
            "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"
        }
        assert "PermissionRequest" not in config  # AgentGuard never answers permission prompts
        for event in ("PreToolUse", "PostToolUse"):
            assert config[event][0]["matcher"] == "Bash|apply_patch"
        for groups in config.values():
            hook = groups[0]["hooks"][0]
            assert hook["type"] == "command"
            assert 1 <= hook["timeout"] <= 60
        assert config["SessionEnd"][0]["hooks"][0]["timeout"] <= 3  # Codex's own cap

    def test_commands_are_shell_safe_argv(self):
        config = inst.build_hook_config(python_exe="/opt/py with space/bin/python")
        command = config["PreToolUse"][0]["hooks"][0]["command"]
        expected = ["/opt/py with space/bin/python", "-P", "-m", inst.HOOK_MODULE, "pre-tool-use"]
        assert shlex.split(command) == expected

    def test_hook_commands_never_put_the_repository_on_sys_path(self):
        # Codex runs hooks in the developer's repository; without -P, `python -m` would let a
        # repository file such as json.py shadow a module the hook imports.
        for groups in inst.build_hook_config(python_exe="/py").values():
            argv = shlex.split(groups[0]["hooks"][0]["command"])
            assert argv.index("-P") < argv.index("-m")

    def test_entries_written_before_dash_p_are_still_ours(self):
        old = {"type": "command", "command": shlex.join(["/py", "-m", inst.HOOK_MODULE, "stop"])}
        assert inst._is_ours_hook(old), "an upgrade must recognise and replace its own old entries"

    def test_every_command_is_recognised_as_ours(self):
        for groups in inst.build_hook_config().values():
            assert inst._is_ours_hook(groups[0]["hooks"][0])

    def test_a_lookalike_user_hook_is_not_ours(self):
        assert not inst._is_ours_hook(LOOKALIKE)
        assert not inst._is_ours_hook(USER_HOOK)
        assert not inst._is_ours_hook({"type": "mcp_tool", "server": "x", "tool": "y"})


class TestInstall:
    def test_creates_a_codex_hooks_file(self, tmp_path):
        path = tmp_path / "hooks.json"
        doc, changed = inst.install(path, python_exe="/py")
        assert changed and path.exists()
        on_disk = json.loads(path.read_text())
        assert set(on_disk) == {"description", "hooks"}  # Codex's HooksFile denies unknown keys
        assert on_disk == doc
        assert inst.is_installed(path)

    def test_is_idempotent(self, tmp_path):
        path = tmp_path / "hooks.json"
        inst.install(path, python_exe="/py")
        first = path.read_text()
        _, changed = inst.install(path, python_exe="/py")
        assert not changed
        assert path.read_text() == first

    def test_reinstall_replaces_instead_of_duplicating(self, tmp_path):
        path = tmp_path / "hooks.json"
        inst.install(path, python_exe="/old/python")
        inst.install(path, python_exe="/new/python")
        doc = json.loads(path.read_text())
        commands = [h["command"] for g in doc["hooks"]["PreToolUse"] for h in g["hooks"]]
        assert len(commands) == 1 and commands[0].startswith("/new/python")

    def test_preserves_user_hooks_and_description(self, tmp_path):
        path = tmp_path / "hooks.json"
        mixed = {"matcher": "Bash", "hooks": [USER_HOOK, LOOKALIKE]}
        path.write_text(json.dumps({"description": "mine", "hooks": {"PreToolUse": [mixed]}}))
        inst.install(path, python_exe="/py")
        doc = json.loads(path.read_text())
        assert doc["description"] == "mine"
        assert doc["hooks"]["PreToolUse"][0] == mixed
        assert len(doc["hooks"]["PreToolUse"]) == 2

    def test_dry_run_writes_nothing(self, tmp_path):
        path = tmp_path / "hooks.json"
        _, changed = inst.install(path, dry_run=True)
        assert changed and not path.exists()

    @pytest.mark.parametrize("content", ["{not json", "[1, 2]"])
    def test_refuses_to_overwrite_what_it_cannot_read(self, tmp_path, content):
        path = tmp_path / "hooks.json"
        path.write_text(content)
        with pytest.raises(RuntimeError):
            inst.install(path)
        assert path.read_text() == content


class TestUninstall:
    def test_removes_only_ours(self, tmp_path):
        path = tmp_path / "hooks.json"
        path.write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [USER_HOOK]}]}}))
        inst.install(path, python_exe="/py")
        _, changed = inst.uninstall(path)
        assert changed
        doc = json.loads(path.read_text())
        assert doc["hooks"] == {"PreToolUse": [{"hooks": [USER_HOOK]}]}
        assert not inst.is_installed(path)

    def test_a_file_that_only_held_our_hooks_is_removed(self, tmp_path):
        path = tmp_path / "hooks.json"
        inst.install(path)
        inst.uninstall(path)
        assert not path.exists()

    def test_is_idempotent_and_tolerates_absence(self, tmp_path):
        path = tmp_path / "hooks.json"
        assert inst.uninstall(path) == ({}, False)
        path.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [USER_HOOK]}]}}))
        before = path.read_text()
        assert inst.uninstall(path)[1] is False
        assert path.read_text() == before


class TestLocations:
    def test_global_honours_codex_home(self, codex_home):
        assert inst.global_hooks_path() == codex_home / "hooks.json"

    def test_project_scope(self, tmp_path):
        assert inst.hooks_path(project=True, workspace=tmp_path) == tmp_path / ".codex" / "hooks.json"

    def test_ambiguous_scope_is_rejected(self):
        with pytest.raises(ValueError):
            inst.hooks_path(project=True, global_=True)


class TestCli:
    def test_install_and_uninstall_codex_globally(self, codex_home):
        runner = CliRunner()
        result = runner.invoke(app, ["install", "codex", "--global"])
        assert result.exit_code == 0, result.output
        assert "/hooks" in result.output  # tells the developer about Codex's trust review
        assert inst.is_installed(codex_home / "hooks.json")

        result = runner.invoke(app, ["uninstall", "codex", "--global"])
        assert result.exit_code == 0, result.output
        assert not (codex_home / "hooks.json").exists()

    def test_install_codex_for_one_project(self, codex_home, tmp_path, monkeypatch):
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.chdir(project)
        result = CliRunner().invoke(app, ["install", "codex", "--project"])
        assert result.exit_code == 0, result.output
        assert inst.is_installed(project / ".codex" / "hooks.json")
        assert not (codex_home / "hooks.json").exists()

    def test_dry_run_and_unknown_agent(self, codex_home):
        runner = CliRunner()
        result = runner.invoke(app, ["install", "codex", "--dry-run"])
        assert result.exit_code == 0 and "dry run" in result.output
        assert not (codex_home / "hooks.json").exists()
        assert runner.invoke(app, ["install", "cursor"]).exit_code == 2

    def test_claude_install_is_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["install", "claude", "--project", "--dry-run"])
        assert result.exit_code == 0
        assert "settings.local.json" in result.output


class TestDoctor:
    def test_reports_untrusted_codex_hooks_as_a_problem(self, codex_home, monkeypatch):
        from agentguard.adapters.codex import status

        inst.install(codex_home / "hooks.json")
        monkeypatch.setattr(status, "codex_version", lambda executable=None: "codex-cli 0.166.0")
        report = status.TrustReport(
            hooks=[
                status.HookTrust(key="k", event="preToolUse", trust="untrusted", enabled=True, plugin_id=None)
            ]
        )
        monkeypatch.setattr(status, "hook_trust", lambda cwd, timeout=30.0, executable=None: report)
        result = CliRunner().invoke(app, ["doctor"])
        assert "codex" in result.output
        assert "need review" in result.output
        assert result.exit_code == 1

    def test_trusted_codex_hooks_satisfy_doctor_without_claude(self, codex_home, monkeypatch):
        from agentguard.adapters.codex import status

        inst.install(codex_home / "hooks.json")
        monkeypatch.setattr(status, "codex_version", lambda executable=None: "codex-cli 0.166.0")
        report = status.TrustReport(
            hooks=[status.HookTrust(key="k", event="stop", trust="trusted", enabled=True, plugin_id=None)]
        )
        monkeypatch.setattr(status, "hook_trust", lambda cwd, timeout=30.0, executable=None: report)
        result = CliRunner().invoke(app, ["doctor"])
        assert "AgentGuard hooks are trusted" in result.output
        assert "no Claude Code or Codex hooks installed" not in result.output
