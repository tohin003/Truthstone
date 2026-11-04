"""Config robustness (R11): one bad value costs that value, never the file or the port.

Before: one invalid value anywhere (`max_per_task = -1`) discarded the whole file, so a
configured `port = 9999` silently became 8787 while the installed hooks still pointed at
9999; typo keys were ignored without a word; `latency.*` and `log_level` did nothing;
`AGENTGUARD_HOME=""` put the token in the project directory and chmod-ed it 0700; and a
symlinked home ancestor (Fedora Silverblue's /home -> var/home) made AgentGuard refuse
to run.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentguard.cli.main import app
from agentguard.core.config import (
    Settings,
    agentguard_home,
    configure_logging,
    daemon_config_error,
    describe_unknown_key,
    ensure_private_dir,
    get_or_create_token,
)
from agentguard.core.store import Database
from agentguard.daemon import private_paths


def _write_config(home: Path, text: str) -> None:
    (home / "config.toml").write_text(text, encoding="utf-8")


class TestFieldByFieldFallback:
    def test_one_bad_field_keeps_port(self, isolated_home):
        _write_config(isolated_home, "[daemon]\nport = 9999\n[challenge]\nmax_per_task = -1\n")
        settings = Settings.load()
        assert settings.daemon.port == 9999, "an unrelated bad value must not move the daemon"
        assert settings.challenge.max_per_task == 6
        assert len(settings.config_warnings) == 1
        assert "challenge.max_per_task = -1" in settings.config_warnings[0]
        assert "using the default 6" in settings.config_warnings[0]
        assert daemon_config_error(settings) is None

    def test_every_bad_field_is_reported_and_every_good_one_kept(self, isolated_home):
        _write_config(
            isolated_home,
            'observe_only = true\n[daemon]\nport = 9999\n[index]\nmax_files = 0\nexclude_dirs = ["a", 3]\n'
            '[challenge]\nmin_severity = "hgih"\nmax_per_fingerprint = 2\n',
        )
        settings = Settings.load()
        assert settings.observe_only is True
        assert settings.daemon.port == 9999
        assert settings.challenge.max_per_fingerprint == 2
        assert settings.index.max_files == 200_000
        assert settings.challenge.min_severity == "medium"
        assert ".venv" in settings.index.exclude_dirs  # the whole list falls back
        reported = " | ".join(settings.config_warnings)
        for key in ("index.max_files", "index.exclude_dirs", "challenge.min_severity"):
            assert key in reported
        assert settings.config_warning.endswith("(and 2 more)")

    def test_a_section_of_the_wrong_type_falls_back_alone(self, isolated_home):
        _write_config(isolated_home, 'challenge = "loud"\n[daemon]\nport = 9999\n')
        settings = Settings.load()
        assert settings.daemon.port == 9999
        assert settings.challenge.max_per_task == 6
        assert "using its defaults" in settings.config_warnings[0]


class TestUnknownKeys:
    def test_unknown_key_reported(self, isolated_home):
        _write_config(
            isolated_home,
            "enabld = false\n[daemon]\nprot = 9999\n[challange]\nmax_per_task = 1\n"
            "[latency]\nhook_timeout_ms = 1\n",
        )
        settings = Settings.load()
        assert settings.unknown_keys == [
            "enabld",
            "daemon.prot",
            "challange.max_per_task",
            "latency.hook_timeout_ms",
        ]
        assert settings.enabled is True and settings.config_warnings == []
        hints = [describe_unknown_key(key) for key in settings.unknown_keys]
        assert "did you mean enabled?" in hints[0]
        assert "did you mean daemon.port?" in hints[1]
        assert "did you mean challenge?" in hints[2]
        assert "removed" in hints[3]

    def test_known_keys_are_not_reported(self, isolated_home):
        _write_config(isolated_home, 'log_level = "info"\n[daemon]\nport = 9999\n[disk]\nlow_free_mb = 1\n')
        assert Settings.load().unknown_keys == []


class TestInvalidDaemonEndpoint:
    @pytest.mark.parametrize(
        ("text", "key"),
        [
            ("[daemon]\nport = 70000\n", "daemon.port"),
            ('[daemon]\nport = "abc"\n', "daemon.port"),
            ('[daemon]\nhost = "0.0.0.0"\nport = 9999\n', "daemon.host"),
            ("daemon = 5\n", "daemon"),
        ],
    )
    def test_invalid_daemon_value_refuses_to_start(self, isolated_home, text, key):
        _write_config(isolated_home, text)
        problem = daemon_config_error(Settings.load())
        assert problem and key in problem and "refusing to start the daemon" in problem

    def test_unparseable_file_that_configures_the_daemon_refuses(self, isolated_home):
        _write_config(isolated_home, "[daemon]\nport = \n")
        assert "cannot be parsed" in daemon_config_error(Settings.load())

    def test_unparseable_file_without_a_daemon_section_still_starts(self, isolated_home):
        _write_config(isolated_home, "enabled = \n")
        settings = Settings.load()
        assert settings.config_warnings and daemon_config_error(settings) is None

    def test_cli_refuses_to_start_run_or_install(self, isolated_home, tmp_path, monkeypatch):
        _write_config(isolated_home, "[daemon]\nport = 70000\n")
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        for args in (["daemon", "start"], ["daemon", "run"], ["install", "claude", "--project"]):
            result = runner.invoke(app, args)
            assert result.exit_code == 2, (args, result.output)
            assert "daemon.port" in result.output
        assert not (tmp_path / ".claude" / "settings.local.json").exists(), "no hooks with a guessed URL"


class TestHome:
    def test_empty_home_env_is_unset(self, tmp_path, monkeypatch):
        from agentguard.adapters.claude_code import shim

        fake_home = tmp_path / "user"
        fake_home.mkdir()
        project = tmp_path / "project"
        project.mkdir(mode=0o755)
        os.chmod(project, 0o755)
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("AGENTGUARD_HOME", "")
        monkeypatch.chdir(project)

        assert agentguard_home() == fake_home / ".agentguard"
        assert str(agentguard_home()) == shim._home(), "the config and the shim must agree"
        get_or_create_token()
        assert (fake_home / ".agentguard" / "token").is_file()
        assert list(project.iterdir()) == [], "no credentials in the project directory"
        assert stat.S_IMODE(project.stat().st_mode) == 0o755, "and its mode left alone"

    def test_symlinked_home_ancestor_works(self, tmp_path, monkeypatch):
        real = tmp_path / "var-home"
        (real / "alice").mkdir(parents=True)
        link = tmp_path / "home"
        link.symlink_to(real, target_is_directory=True)  # /home -> var/home, on Silverblue
        configured = link / "alice" / ".agentguard"
        monkeypatch.setenv("AGENTGUARD_HOME", str(configured))
        Database.reset_shared()

        home = agentguard_home()
        assert home == real.resolve() / "alice" / ".agentguard", "resolved once, at the boundary"
        assert ensure_private_dir() == home
        _write_config(home, "[daemon]\nport = 9999\n")
        assert Settings.load().daemon.port == 9999
        token = get_or_create_token()
        assert (home / "token").read_text() == token
        assert not Database.shared().degraded_reason
        assert (configured / "agentguard.db").exists(), "same files, whichever spelling"

    def test_a_link_another_user_could_swap_is_still_refused(self, tmp_path, monkeypatch):
        shared = tmp_path / "shared"
        shared.mkdir()
        os.chmod(shared, 0o777)  # world-writable, not sticky: anyone can replace the link
        target = tmp_path / "target"
        target.mkdir()
        (shared / "link").symlink_to(target, target_is_directory=True)
        monkeypatch.setenv("AGENTGUARD_HOME", str(shared / "link" / "agentguard"))

        with pytest.raises(RuntimeError, match="symlinked"):
            ensure_private_dir()
        assert not (target / "agentguard").exists()

    def test_root_owned_system_links_are_accepted_for_any_private_path(self, tmp_path, monkeypatch):
        """Silverblue's /home -> var/home is root's; installing into ~/.claude must work."""
        real = tmp_path / "var-home"
        real.mkdir()
        link = tmp_path / "home"
        link.symlink_to(real, target_is_directory=True)
        with pytest.raises(RuntimeError):
            ensure_private_dir(link / "alice" / ".claude")  # a user's link: refused
        monkeypatch.setattr(private_paths, "ROOT_UID", os.getuid())  # stand in for root
        assert ensure_private_dir(link / "alice" / ".claude").is_dir()


class TestLogLevel:
    def test_log_level_is_validated(self, isolated_home):
        _write_config(isolated_home, 'log_level = "debug"\n')
        assert Settings.load().log_level == "DEBUG"
        _write_config(isolated_home, 'log_level = "loud"\n')
        settings = Settings.load()
        assert settings.log_level == "WARNING"
        assert "log_level" in settings.config_warnings[0]

    def test_log_level_is_applied(self, isolated_home):
        logger = logging.getLogger("agentguard")
        previous_level, previous_handlers = logger.level, list(logger.handlers)
        try:
            _write_config(isolated_home, 'log_level = "debug"\n')
            configure_logging(Settings.load())
            assert logger.level == logging.DEBUG
            assert logging.getLogger("agentguard.core.store").isEnabledFor(logging.DEBUG)
        finally:
            logger.setLevel(previous_level)
            logger.handlers[:] = previous_handlers

    def test_latency_section_is_retired(self):
        assert "latency" not in Settings.model_fields
