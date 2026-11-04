"""`python -m agentguard.daemon run` honours config.toml the way the CLI does (R11).

The shim and `agentguard daemon start` both spawn ``python -m agentguard.daemon run`` with
no ``--port``. Only `agentguard daemon run` used to refuse an invalid ``[daemon]`` section
and apply ``log_level``; the spawned daemon fell back to 127.0.0.1:8787 — a port the
installed hooks may not point at — and ignored the configured log level.
"""

from __future__ import annotations

import logging
import signal
import socket
import sys

import pytest
import uvicorn

from agentguard.daemon import __main__ as daemon_main
from agentguard.daemon import app as daemon_app


@pytest.fixture
def restore_process_state():
    """`run()` configures process-wide logging and signal handlers; put them back."""
    loggers = [logging.getLogger(), logging.getLogger("agentguard")]
    saved = [(lg, lg.level, list(lg.handlers)) for lg in loggers]
    signals = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield
    for lg, level, handlers in saved:
        lg.setLevel(level)
        lg.handlers[:] = handlers
    for sig, handler in signals.items():
        signal.signal(sig, handler)


@pytest.fixture
def no_server(monkeypatch):
    """Let `run()` get as far as serving, then return instead of serving forever."""
    served = []
    monkeypatch.setattr(uvicorn.Server, "run", lambda self, sockets=None: served.append(sockets))
    return served


def _write_config(home, text: str) -> None:
    (home / "config.toml").write_text(text, encoding="utf-8")


def test_daemon_run_refuses_invalid_port_config(isolated_home, monkeypatch, capsys, restore_process_state):
    _write_config(isolated_home, "[daemon]\nport = 70000\n")
    sockets = []

    class NoSocket:
        """Nothing may bind: the fallback would be the default port, 8787."""

        def __init__(self, *args, **kwargs):
            sockets.append(args)
            raise AssertionError("the daemon tried to bind despite an invalid [daemon] section")

    monkeypatch.setattr(socket, "socket", NoSocket)
    monkeypatch.setattr(sys, "argv", ["agentguard.daemon", "run"])  # exactly what the shim spawns
    with pytest.raises(SystemExit) as exited:
        daemon_main.main()

    assert exited.value.code == 2
    err = capsys.readouterr().err
    assert "daemon.port" in err and "refusing to start the daemon" in err
    assert not sockets
    assert not (isolated_home / "daemon.json").exists()
    assert not (isolated_home / "token").exists(), "refused before touching credentials"


def test_daemon_run_refuses_an_unparseable_config_that_configures_the_daemon(
    isolated_home, monkeypatch, capsys, restore_process_state
):
    _write_config(isolated_home, "[daemon]\nport = \n")
    monkeypatch.setattr(socket, "socket", None)  # any bind attempt fails loudly
    with pytest.raises(SystemExit) as exited:
        daemon_app.run()
    assert exited.value.code == 2
    assert "cannot be parsed" in capsys.readouterr().err


def test_an_explicit_port_still_starts(isolated_home, no_server, restore_process_state):
    """Tests and a developer debugging by hand pass `--port`: that is not a guess."""
    _write_config(isolated_home, "[daemon]\nport = 70000\n")
    daemon_app.run(port=0)
    assert len(no_server) == 1, "it got as far as serving"
    assert not (isolated_home / "daemon.json").exists(), "and cleaned up its handshake"


def test_daemon_applies_log_level(isolated_home, no_server, restore_process_state):
    logger = logging.getLogger("agentguard")
    logger.setLevel(logging.NOTSET)
    _write_config(isolated_home, 'log_level = "debug"\n')
    daemon_app.run(port=0)
    assert logger.level == logging.DEBUG
    assert logging.getLogger("agentguard.core.store").isEnabledFor(logging.DEBUG)

    _write_config(isolated_home, 'log_level = "error"\n')
    daemon_app.run(port=0)
    assert logger.level == logging.ERROR
    assert not logging.getLogger("agentguard.daemon.app").isEnabledFor(logging.WARNING)
