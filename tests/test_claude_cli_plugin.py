"""`agentguard install claude` and `doctor` know about the plugin (migration).

The settings-based install stays as the fallback, so both can end up present. Neither
command may hide that: `install` points at the plugin (or says the plugin is already
there), and `doctor` reports the plugin, the duplicate, and stops calling a
plugin-guarded project "unguarded".
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentguard.adapters.claude_code import install as inst
from agentguard.cli.main import app

runner = CliRunner()


@pytest.fixture
def claude_config(tmp_path, monkeypatch):
    config = tmp_path / "claude-config"
    config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.delenv("AGENTGUARD_PLUGIN_DATA", raising=False)
    return config, project


def record_plugin(config, scope="user", project=None):
    entry = {"scope": scope, "installPath": "/cache/agentguard/0.1.0", "version": "0.1.0"}
    if project is not None:
        entry["projectPath"] = str(project)
    path = config / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 2, "plugins": {"agentguard@agentguard": [entry]}}))


class TestInstallExplainsThePlugin:
    def test_points_at_the_plugin(self, claude_config):
        result = runner.invoke(app, ["install", "claude", "--project", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "/plugin marketplace add tohin003/AgentGuard" in result.output
        assert "/plugin install agentguard@agentguard" in result.output

    def test_warns_when_the_plugin_is_already_there(self, claude_config):
        config, _ = claude_config
        record_plugin(config)
        result = runner.invoke(app, ["install", "claude", "--project", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "plugin is also installed" in result.output
        assert "stands down" in result.output


class TestDoctor:
    def test_the_plugin_alone_is_not_unguarded(self, claude_config):
        config, _ = claude_config
        record_plugin(config)
        result = runner.invoke(app, ["doctor"])
        assert "plugin agentguard@agentguard installed" in result.output
        assert "currently unguarded" not in result.output

    def test_both_installs_are_reported(self, claude_config):
        config, project = claude_config
        record_plugin(config, scope="local", project=project)
        inst.install(project / ".claude" / "settings.local.json")
        result = runner.invoke(app, ["doctor"])
        assert "installed twice" in result.output
        assert "agentguard uninstall claude" in result.output

    def test_inside_a_plugin_session(self, claude_config, monkeypatch, tmp_path):
        """/agentguard:doctor runs with AGENTGUARD_PLUGIN_DATA: proof the plugin is live,
        even when it was loaded for one session with --plugin-dir and has no record."""
        monkeypatch.setenv("AGENTGUARD_PLUGIN_DATA", str(tmp_path / "plugin-data"))
        result = runner.invoke(app, ["doctor"])
        assert "plugin runtime:" in result.output
        assert "currently unguarded" not in result.output

    def test_nothing_installed_is_still_unguarded(self, claude_config):
        result = runner.invoke(app, ["doctor"])
        assert "plugin not installed" in result.output
        assert "currently unguarded" in result.output
