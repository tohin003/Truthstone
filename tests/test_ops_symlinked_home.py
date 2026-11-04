"""A home behind a trusted symlink works for every entry point; an untrusted one for none
(R11).

`core/config.py` already resolved a symlinked home ancestor that root or the user placed
where nobody else can change it (Fedora Silverblue's `/home -> var/home`, a dotfiles
link). The lifecycle helpers, the Claude shim and the Codex hook did not: the shim's
`_home()` kept the link, `daemon/lifecycle.py` refused it, and `shim.ensure_daemon`
could never take its startup lock — no daemon, every hook failing open. They now share
one rule (`daemon/private_paths.py`).
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import shim
from agentguard.adapters.codex import hook as codex_hook
from agentguard.core.config import agentguard_home, ensure_private_dir
from agentguard.daemon import lifecycle, private_paths
from tests.conftest import REPO_ROOT, free_port


def _symlinked_home(tmp_path: Path, parent_mode: int = 0o755) -> tuple[Path, Path]:
    """`<tmp>/home -> <tmp>/var-home`, with `alice/.agentguard` below it.
    Returns (the configured home, through the link; its real location)."""
    holder = tmp_path / "layout"
    holder.mkdir()
    real = holder / "var-home" / "alice" / ".agentguard"
    real.mkdir(parents=True, mode=0o700)
    (holder / "home").symlink_to(holder / "var-home", target_is_directory=True)
    os.chmod(holder, parent_mode)
    return holder / "home" / "alice" / ".agentguard", real


def _stop(hs: dict) -> None:
    os.kill(hs["pid"], signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline and shim._alive(hs):
        time.sleep(0.05)
    assert not shim._alive(hs), "the daemon this test started is gone"


def test_shim_ensure_daemon_works_under_trusted_symlinked_home(tmp_path, monkeypatch):
    configured, real = _symlinked_home(tmp_path)  # the user's own link, in a 0755 directory
    (real / "config.toml").write_text(f"[daemon]\nport = {free_port()}\n", encoding="utf-8")
    monkeypatch.setenv("AGENTGUARD_HOME", str(configured))
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT / "src"))  # the daemon runs this checkout

    hs = shim.ensure_daemon(timeout=20)
    assert hs is not None, "the startup lock was taken and a daemon started"
    try:
        canonical = os.path.realpath(real)
        assert shim._home() == codex_hook._home() == str(agentguard_home()) == canonical, (
            "every entry point finds the same home"
        )
        assert shim.health_body(hs) is not None
        assert (real / "daemon.json").is_file() and (real / "daemon.start.lock").is_file()
        assert codex_hook._handshake() == hs
        lifecycle_hs, notice, health = codex_hook._lifecycle()
        assert lifecycle_hs == hs and notice == "" and health["pid"] == hs["pid"]
    finally:
        _stop(hs)


def test_untrusted_symlink_still_refused(tmp_path, monkeypatch):
    """A link in a directory anyone can write could be swapped to redirect credentials."""
    configured, real = _symlinked_home(tmp_path, parent_mode=0o777)  # world-writable, not sticky
    monkeypatch.setenv("AGENTGUARD_HOME", str(configured))

    assert shim._home() == str(configured), "left as configured, so the checks refuse it"
    assert private_paths.resolve_home(str(configured)) == (str(configured), False)
    with pytest.raises(RuntimeError, match="symlinked"):
        ensure_private_dir()
    assert shim.ensure_daemon(timeout=0.5) is None
    assert not (real / "daemon.start.lock").exists(), "no lock taken through the link"
    with pytest.raises(OSError):
        lifecycle.open_private_append(configured / "daemon.log")

    # A handshake planted behind the link names where hooks would send the token.
    planted = {"pid": os.getpid(), "host": "127.0.0.1", "port": free_port(), "token": "x"}
    (real / "daemon.json").write_text(json.dumps(planted), encoding="utf-8")
    assert shim._handshake() is None
    assert codex_hook._handshake() is None


def test_root_owned_system_links_are_trusted_by_the_lifecycle_helpers_too(tmp_path, monkeypatch):
    """Silverblue's `/home -> var/home` is root's. config accepted it for any private
    path; the lock, log and marker helpers only knew macOS's /tmp and /var."""
    real = tmp_path / "var-home"
    real.mkdir()
    link = tmp_path / "home"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        lifecycle.open_private_append(link / "alice" / "daemon.log")  # a user's link: refused

    monkeypatch.setattr(private_paths, "ROOT_UID", os.getuid())  # stand in for root
    lifecycle.open_private_append(link / "alice" / "daemon.log").close()
    assert lifecycle.create_private_marker(link / "alice" / "marker", "x")
    with lifecycle.interprocess_lock(lifecycle.startup_lock_path(link / "alice"), timeout=0.1) as locked:
        assert locked
    assert ensure_private_dir(link / "alice").is_dir(), "and config agrees"


def test_every_entry_point_agrees_on_the_home(tmp_path, monkeypatch):
    configured, real = _symlinked_home(tmp_path)
    cases = {
        "trusted link": str(configured),
        "plain": str(real),
        "relative": "rel/.agentguard",
        "trailing slash": f"{configured}/",
    }
    monkeypatch.chdir(tmp_path)
    for label, value in cases.items():
        monkeypatch.setenv("AGENTGUARD_HOME", value)
        assert shim._home() == codex_hook._home() == str(agentguard_home()), label
    monkeypatch.setenv("AGENTGUARD_HOME", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert shim._home() == str(agentguard_home()) == str(tmp_path / ".agentguard")


def test_resolving_the_home_never_raises(monkeypatch):
    """The hooks call this on every tool call; they must never crash the host."""
    assert private_paths.resolve_home("/no\0such") == ("/no\0such", False)
    monkeypatch.setattr(os, "getcwd", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    assert private_paths.resolve_home("relative/home") == ("relative/home", False)
