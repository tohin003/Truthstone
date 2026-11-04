"""Finding AgentGuard in Claude Code's configuration (settings hooks and the plugin).

Both installs at once would handle every event twice, so each side has to be able to see
the other. These tests pin what "seeing" means: the same ownership test the installer uses,
every settings file Claude Code reads for a session, and the plugin's own install records.
"""

from __future__ import annotations

import json

import pytest

from agentguard.adapters.claude_code import install as inst
from agentguard.adapters.claude_code import settings_scan as scan


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    path = tmp_path / "claude-config"
    path.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(path))
    return path


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "project"
    (path / ".claude").mkdir(parents=True)
    return path


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def installed_plugins(config_dir, plugins):
    write(config_dir / "plugins" / "installed_plugins.json", {"version": 2, "plugins": plugins})


class TestLegacyHooks:
    def test_finds_each_scope_claude_code_reads(self, config_dir, project):
        inst.install(config_dir / "settings.json")
        inst.install(project / ".claude" / "settings.local.json")
        found = scan.legacy_hook_files(project)
        assert [scope for scope, _ in found] == ["user", "local"]

    def test_committed_project_settings_count_too(self, config_dir, project):
        hooks = inst.build_hook_config()
        write(project / ".claude" / "settings.json", {"hooks": hooks})
        assert [scope for scope, _ in scan.legacy_hook_files(project)] == ["project"]

    def test_a_users_own_hooks_are_not_ours(self, config_dir, project):
        mine = {"hooks": [{"type": "command", "command": "echo agentguard is great"}]}
        write(config_dir / "settings.json", {"hooks": {"PreToolUse": [mine]}})
        assert scan.legacy_hook_files(project) == []

    def test_invalid_json_is_not_a_crash(self, config_dir, project):
        (config_dir / "settings.json").write_text("{ not json")
        assert scan.legacy_hook_files(project) == []

    def test_the_installer_and_the_scanner_agree(self, config_dir):
        """One definition of ownership, shared."""
        path = config_dir / "settings.json"
        inst.install(path)
        assert scan.hooks_installed(path) is inst.is_installed(path) is True
        inst.uninstall(path)
        assert scan.hooks_installed(path) is inst.is_installed(path) is False


class TestPluginInstalls:
    def test_reads_install_records(self, config_dir, project):
        installed_plugins(
            config_dir,
            {
                "agentguard@agentguard": [
                    {"scope": "user", "installPath": "/x", "version": "0.1.0"},
                ],
                "other@market": [{"scope": "user"}],
            },
        )
        found = scan.plugin_installs()
        assert [(p.plugin_id, p.scope, p.version) for p in found] == [
            ("agentguard@agentguard", "user", "0.1.0")
        ]
        assert scan.active_plugin_installs(project)

    def test_a_project_scoped_install_applies_only_there(self, config_dir, project, tmp_path):
        installed_plugins(
            config_dir,
            {"agentguard@agentguard": [{"scope": "local", "projectPath": str(project)}]},
        )
        assert scan.active_plugin_installs(project)
        assert scan.active_plugin_installs(project / "sub" / "dir")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        assert scan.active_plugin_installs(elsewhere) == []

    def test_disabled_in_settings_is_not_active(self, config_dir, project):
        installed_plugins(config_dir, {"agentguard@agentguard": [{"scope": "user"}]})
        write(config_dir / "settings.json", {"enabledPlugins": {"agentguard@agentguard": False}})
        assert scan.active_plugin_installs(project) == []

    def test_local_settings_override_user_settings(self, config_dir, project):
        """Claude Code's precedence: local > project > user."""
        installed_plugins(config_dir, {"agentguard@agentguard": [{"scope": "user"}]})
        write(config_dir / "settings.json", {"enabledPlugins": {"agentguard@agentguard": False}})
        write(
            project / ".claude" / "settings.local.json",
            {"enabledPlugins": {"agentguard@agentguard": True}},
        )
        assert scan.plugin_enabled_setting("agentguard@agentguard", project) is True
        assert scan.active_plugin_installs(project)

    def test_no_records_means_no_plugin(self, config_dir, project):
        assert scan.plugin_installs() == []
        assert scan.active_plugin_installs(project) == []
