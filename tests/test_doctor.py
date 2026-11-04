"""`truthstone doctor` (R11): never crashes, and checks what actually breaks guarding.

Before: a corrupted database crashed it; it said "✓ hooks installed" while those hooks
carried another home's token (so the daemon rejected every one); it never looked at
the running daemon's mode; it said nothing about a missing tree-sitter extra; and it
warned about `rg`, which nothing uses.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

import truthstone.cli.main as cli
from truthstone.adapters.claude_code import install as claude_install
from truthstone.core.config import Settings

SECTIONS = ("environment", "config", "storage", "daemon", "claude code", "codex")


@pytest.fixture
def doctor_env(isolated_home, tmp_path, monkeypatch):
    """Hermetic: no real ~/.claude, ~/.codex or codex binary, and a scratch project."""
    from truthstone.adapters.codex import status

    claude_config = tmp_path / "claude-config"
    claude_config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_config))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.delenv("TRUTHSTONE_PLUGIN_DATA", raising=False)
    monkeypatch.setattr(status, "codex_version", lambda executable=None: None)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return isolated_home, claude_config, project


def run_doctor() -> tuple[int, str]:
    result = CliRunner().invoke(cli.app, ["doctor"])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    return result.exit_code, result.output


def test_doctor_survives_corrupted_db(doctor_env):
    home, _, _ = doctor_env
    (home / "truthstone.db").write_bytes(b"this is not a sqlite database" * 200)
    code, output = run_doctor()
    assert code == 1
    for section in SECTIONS:
        assert section in output
    assert "persistence is OFF" in output and "corrupted" in output


def test_doctor_survives_a_section_that_raises(doctor_env, monkeypatch):
    def broken(report):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(cli, "_doctor_storage", broken)
    code, output = run_doctor()
    assert code == 1
    assert "storage could not be completed: RuntimeError: disk on fire" in output
    assert "claude code" in output and "codex" in output, "later sections still run"


def test_doctor_no_longer_mentions_rg(doctor_env):
    _, output = run_doctor()
    assert "rg " not in output


class TestTreeSitter:
    def test_doctor_warns_missing_treesitter(self, doctor_env, monkeypatch):
        _, _, project = doctor_env
        (project / "src").mkdir()
        for name in ("a.ts", "b.ts", "c.js"):
            (project / "src" / name).write_text("export const x = 1;\n")
        (project / "node_modules" / "dep").mkdir(parents=True)
        (project / "node_modules" / "dep" / "index.js").write_text("module.exports = 1;\n")
        monkeypatch.setattr(cli, "_treesitter_available", lambda: False)

        _, output = run_doctor()

        line = next(ln for ln in output.splitlines() if "tree-sitter extra is not installed" in ln)
        assert line.lstrip().startswith("!"), "a warning, not a failure"
        assert "2 .ts, 1 .js" in line, "node_modules is not counted"
        assert "truthstone[treesitter]" in line

    def test_no_warning_when_nothing_needs_it(self, doctor_env, monkeypatch):
        _, _, project = doctor_env
        (project / "app.py").write_text("x = 1\n")
        monkeypatch.setattr(cli, "_treesitter_available", lambda: False)
        _, output = run_doctor()
        assert "not needed here" in output
        assert "tree-sitter extra is not installed" not in output

    def test_the_scan_is_bounded(self, tmp_path):
        for i in range(50):
            (tmp_path / f"f{i}.ts").write_text("")
        assert sum(cli._files_needing_treesitter(tmp_path, set(), budget=10).values()) < 10


class TestInstalledHooks:
    def _install(self, claude_config: Path) -> Path:
        path = claude_config / "settings.json"
        claude_install.install(path)
        return path

    def test_matching_hooks_are_reported_installed(self, doctor_env):
        _, claude_config, _ = doctor_env
        path = self._install(claude_config)
        _, output = run_doctor()
        assert f"global hooks installed ({path})" in output
        assert "different token" not in output

    def test_doctor_detects_token_mismatch(self, doctor_env):
        home, claude_config, _ = doctor_env
        path = self._install(claude_config)
        (home / "token").write_text("a-token-from-another-truthstone-home", encoding="utf-8")

        code, output = run_doctor()

        assert code == 1
        assert f"global hooks installed ({path})" not in output, "no ✓ for hooks the daemon rejects"
        assert "carry a different token than" in output
        assert "truthstone install claude --global" in output
        assert "a-token-from-another" not in output, "never print a token"

    def test_doctor_detects_hook_url_mismatch(self, doctor_env):
        home, claude_config, _ = doctor_env
        self._install(claude_config)
        old_port = Settings.load().daemon.port
        (home / "config.toml").write_text(f"[daemon]\nport = {old_port + 1}\n", encoding="utf-8")

        code, output = run_doctor()

        assert code == 1
        assert f"post to http://127.0.0.1:{old_port}/hook/claude-code" in output
        assert f"configured for http://127.0.0.1:{old_port + 1}/hook/claude-code" in output

    def test_settings_files_are_only_read(self, doctor_env):
        home, claude_config, _ = doctor_env
        path = self._install(claude_config)
        (home / "token").write_text("another", encoding="utf-8")
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        run_doctor()
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before


class TestRunningDaemon:
    @pytest.fixture
    def live(self, doctor_env, monkeypatch):
        """A daemon that answers /health with whatever the test sets."""
        import truthstone.adapters.codex.hook as codex_hook
        import truthstone.daemon.app as daemon_app

        home, _, _ = doctor_env
        settings = Settings.load()
        token = "the-current-token"
        (home / "token").write_text(token, encoding="utf-8")
        handshake = {"pid": os.getpid(), "host": "127.0.0.1", "port": settings.daemon.port, "token": token}
        health = {"status": "ok", "pid": os.getpid(), "enabled": True, "observing": False}
        monkeypatch.setattr(daemon_app, "daemon_is_alive", lambda: True)
        monkeypatch.setattr(daemon_app, "read_handshake", lambda: dict(handshake))
        monkeypatch.setattr(codex_hook, "_health", lambda hs: dict(health))
        return handshake, health

    def test_healthy_daemon_is_ok(self, live):
        _, output = run_doctor()
        assert "running (pid" in output
        assert "OBSERVE-ONLY" not in output and "DISABLED" not in output

    def test_doctor_reads_health_observing(self, live):
        _, health = live
        health["observing"] = True
        code, output = run_doctor()
        assert code == 1
        assert "the running daemon is OBSERVE-ONLY, so no session is guarded" in output

    def test_doctor_reads_health_enabled(self, live):
        _, health = live
        health["enabled"] = False
        _, output = run_doctor()
        assert "the running daemon is DISABLED" in output

    def test_doctor_shows_degraded_reasons(self, live):
        _, health = live
        health["degraded"] = ["index unavailable: too large"]
        _, output = run_doctor()
        assert "degraded: index unavailable: too large" in output

    def test_doctor_detects_a_daemon_on_another_port_or_token(self, live):
        handshake, _ = live
        handshake["port"] += 1
        handshake["token"] = "an-older-token"
        _, output = run_doctor()
        assert "but config.toml says" in output
        assert "runs with a different token" in output


def test_doctor_reports_config_problems(doctor_env):
    home, _, _ = doctor_env
    port = Settings.load().daemon.port
    (home / "config.toml").write_text(
        f"[daemon]\nport = {port}\nprot = 1\n[challenge]\nmax_per_task = -1\n", encoding="utf-8"
    )
    code, output = run_doctor()
    assert code == 1
    assert "challenge.max_per_task = -1" in output
    assert "daemon.prot is ignored (did you mean daemon.port?)" in output
    assert json.dumps(port) in output
