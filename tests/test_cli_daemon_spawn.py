"""`agentguard daemon start` must never import code from the directory it was typed in.

The command is usually run inside a repository. Spawned as `python -m agentguard.daemon` from
there, the daemon would get that directory first on sys.path, and a repository file could
shadow a module the daemon imports.
"""

from __future__ import annotations

import subprocess

from typer.testing import CliRunner

from agentguard.cli import main as cli


def test_daemon_start_uses_dash_p_and_a_safe_cwd(tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("AGENTGUARD_HOME", str(home))
    monkeypatch.chdir(repo)

    calls: list[tuple[list[str], dict]] = []

    class FakePopen:
        def __init__(self, argv, **kwargs):
            calls.append((list(argv), kwargs))

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    result = CliRunner().invoke(cli.app, ["daemon", "start", "--timeout", "0.2"])

    assert calls, f"daemon start never spawned anything: {result.output}"
    argv, kwargs = calls[0]
    assert argv.index("-P") < argv.index("-m"), argv
    assert argv[argv.index("-m") + 1] == "agentguard.daemon"
    assert kwargs.get("cwd") is not None
    assert str(kwargs["cwd"]) != str(repo), "the daemon must not start in the caller's directory"
