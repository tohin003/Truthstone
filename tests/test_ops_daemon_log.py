"""daemon.log never carries a payload value, and never grows without bound (R17).

Before: a malformed hook payload made the daemon log a full traceback, and a pydantic
``ValidationError`` prints ``input_value=...`` — the payload itself, credentials included
(D3's ``x_secrets.py``: the log contained the fake password). daemon.log is the daemon's
stdout/stderr and was never rotated.
"""

from __future__ import annotations

import io
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import BaseModel

from agentguard.daemon import lifecycle, logs
from tests.conftest import REPO_ROOT, free_port

FAKE_KEY = "sk-live-FAKE0123456789abcdefFAKE"
# No label, no known prefix: no pattern can recognise it, so only never logging payload
# values keeps it out.
FAKE_PASSWORD = "hunter2-FAKE-PASSWORD"


class _Event(BaseModel):
    workspace: str


def _validation_error(value: object) -> Exception:
    try:
        _Event(workspace=value)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        return exc
    raise AssertionError("expected a validation error")


# -- end to end: a real daemon, its real log file -------------------------------------------


def _spawn_logged_daemon(home: Path, port: int) -> tuple[subprocess.Popen, Path]:
    """Like the shim: stdout and stderr appended to <home>/daemon.log."""
    log_path = home / "daemon.log"
    log_file = lifecycle.open_private_append(log_path)
    env = dict(os.environ, AGENTGUARD_HOME=str(home), PYTHONPATH=str(REPO_ROOT / "src"))
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "agentguard.daemon", "run", "--port", str(port)],
            env=env,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
        )
    finally:
        log_file.close()
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"daemon exited early:\n{log_path.read_text()}")
        if (home / "daemon.json").exists():
            with socket.socket() as s:
                s.settimeout(0.2)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return proc, log_path
        time.sleep(0.05)
    proc.kill()
    raise TimeoutError("daemon did not start")


def _post(port: int, token: str, route: str, payload: dict) -> int:
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        body = json.dumps(payload)
        conn.request("POST", f"/hook/{route}", body=body, headers={"Authorization": f"Bearer {token}"})
        response = conn.getresponse()
        assert response.read() == b"{}", "fails open"
        return response.status
    finally:
        conn.close()


def test_daemon_log_never_contains_payload_secrets(isolated_home):
    port = free_port()
    proc, log_path = _spawn_logged_daemon(isolated_home, port)
    try:
        token = json.loads((isolated_home / "daemon.json").read_text())["token"]
        # One short secret per payload: pydantic elides the middle of a long input's repr,
        # which would hide a leak from a whole-string check.
        malformed = [
            # pydantic: "input_value={'x': 'hunter2-…'}" in the exception text
            {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": {"x": FAKE_PASSWORD}},
            {"hook_event_name": "PostToolUse", "session_id": "s", "cwd": [FAKE_KEY], "tool_name": "Bash"},
            {"hook_event_name": "PreToolUse", "session_id": {"nested": FAKE_PASSWORD}, "cwd": "/tmp"},
        ]
        for payload in malformed:
            for route in ("claude-code", "codex"):
                assert _post(port, token, route, payload) == 200
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    assert proc.poll() is not None, "the daemon is gone"

    text = log_path.read_text(encoding="utf-8", errors="replace")
    for fragment in (FAKE_PASSWORD, FAKE_KEY, "FAKE-PASS", "abcdefFAKE", "input_value"):
        assert fragment not in text, fragment
    assert "hook handling failed" in text, "the failure is logged, not silent"
    assert "ValidationError" in text, "by exception type"
    assert "workspace: string_type" in text, "and where it happened"


# -- what an exception is allowed to say ----------------------------------------------------


def test_a_validation_error_is_described_without_its_input():
    text = logs.describe_exception(_validation_error({"nested": FAKE_PASSWORD}))
    assert text.startswith("ValidationError: 1 validation error for _Event")
    assert "workspace: string_type" in text
    assert FAKE_PASSWORD not in text and "nested" not in text


def test_other_exceptions_keep_their_type_and_a_redacted_message():
    text = logs.describe_exception(RuntimeError(f"curl -H 'Authorization: Bearer {FAKE_KEY}' failed"))
    assert text.startswith("RuntimeError: curl -H")
    assert FAKE_KEY not in text and "[REDACTED]" in text
    assert logs.describe_exception(KeyError()) == "KeyError"


def test_the_traceback_keeps_frames_and_drops_values():
    try:
        try:
            raise ValueError(f"token={FAKE_KEY}")
        except ValueError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as exc:
        text = logs.safe_traceback(exc)
    assert "Traceback (most recent call last)" in text
    assert "test_the_traceback_keeps_frames_and_drops_values" in text, "frames are kept"
    assert "ValueError: token=sk-[REDACTED]" in text and "RuntimeError: wrapped" in text
    assert FAKE_KEY not in text


def test_any_record_formatted_by_the_daemon_is_safe():
    """Whoever logs — the engine, the index, a library — the formatter decides what is
    written. `log.exception` and an exception passed as an argument both quote values."""
    formatter = logs.SafeFormatter()
    error = _validation_error([FAKE_PASSWORD])
    try:
        raise error
    except Exception:  # noqa: BLE001
        exc_info = sys.exc_info()

    def record(msg, args=(), exc_info=None, level=logging.WARNING):
        return logging.LogRecord("agentguard.x", level, __file__, 1, msg, args, exc_info)

    records = [
        record("handler failed", exc_info=exc_info, level=logging.ERROR),
        record("failed: %s", (error,)),
        record(f"Bearer {FAKE_KEY}"),
        record(error),
        record("%s %s", ("one",)),
    ]
    for record in records:
        text = formatter.format(record)
        assert FAKE_PASSWORD not in text and FAKE_KEY not in text, text
    assert "ValidationError" in formatter.format(records[0])


def test_a_cached_unsafe_traceback_is_not_reused():
    """Another handler may format a record first and cache its traceback text."""
    try:
        raise _validation_error([FAKE_PASSWORD])
    except Exception:  # noqa: BLE001
        record = logging.LogRecord("agentguard", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
    logging.Formatter().format(record)
    assert FAKE_PASSWORD in (record.exc_text or "")
    assert FAKE_PASSWORD not in logs.SafeFormatter().format(record)


# -- rotation -------------------------------------------------------------------------------


def test_rotate_log_moves_only_an_oversized_regular_file(tmp_path):
    log = tmp_path / "daemon.log"
    assert not lifecycle.rotate_log(log, max_bytes=10)  # nothing there
    log.write_text("small")
    assert not lifecycle.rotate_log(log, max_bytes=10)
    for generation in range(4):
        log.write_text(f"generation {generation} " * 3)
        assert lifecycle.rotate_log(log, max_bytes=10, backups=2)
        assert not log.exists()
    assert (tmp_path / "daemon.log.1").read_text().startswith("generation 3")
    assert (tmp_path / "daemon.log.2").read_text().startswith("generation 2")
    assert not (tmp_path / "daemon.log.3").exists(), "only `backups` old files are kept"


def test_rotate_log_never_follows_a_symlink(tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text("x" * 100)
    link = tmp_path / "daemon.log"
    link.symlink_to(target)
    assert not lifecycle.rotate_log(link, max_bytes=10)
    assert target.read_text() == "x" * 100 and link.is_symlink()


def test_the_daemon_rotates_its_own_log_while_it_runs(tmp_path):
    """daemon.log is the daemon's stderr: rotating means a fresh file under the same fd."""
    path = tmp_path / "daemon.log"
    raw = lifecycle.open_private_append(path)
    stream = open(raw.fileno(), "w", buffering=1, encoding="utf-8", closefd=False)  # noqa: SIM115
    handler = logs.DaemonLogHandler(path, stream=stream, fd=raw.fileno(), also=(), max_bytes=400, backups=1)
    logger = logging.getLogger("agentguard.test.rotation")
    logger.propagate = False
    logger.addHandler(handler)
    try:
        for n in range(40):
            logger.warning("line %d %s", n, "x" * 40)
        logger.warning("the last line")
    finally:
        logger.removeHandler(handler)
        logger.propagate = True
        stream.close()
        raw.close()
    current, backup = path.read_text(), (tmp_path / "daemon.log.1").read_text()
    assert "the last line" in current, "writing continued in the fresh file"
    assert "line 39" in current + backup
    assert len(current) < 400 + 200 and len(backup) < 400 + 200, "each file stays bounded"
    assert not (tmp_path / "daemon.log.2").exists()
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_a_handler_whose_stderr_is_not_the_log_never_rotates(tmp_path):
    path = tmp_path / "daemon.log"
    path.write_text("y" * 1000)
    sink = io.StringIO()
    with open(tmp_path / "other.log", "ab") as other:
        handler = logs.DaemonLogHandler(path, stream=sink, fd=other.fileno(), also=(), max_bytes=10)
        other.write(b"z" * 100)
        other.flush()
        handler.emit(logging.LogRecord("agentguard", logging.WARNING, __file__, 1, "hello", (), None))
    assert path.read_text() == "y" * 1000 and not (tmp_path / "daemon.log.1").exists()
    assert not handler.rotates


def test_starting_a_daemon_rotates_an_oversized_log(isolated_home, monkeypatch):
    """The spawners bound it across restarts (the shim here; `daemon start` shares the helper)."""
    from agentguard.adapters.claude_code import shim

    monkeypatch.setattr(lifecycle, "DAEMON_LOG_MAX_BYTES", 1_000)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT / "src"))  # the daemon runs this checkout
    old = "an old run\n" * 200
    (isolated_home / "daemon.log").write_text(old)
    hs = shim.ensure_daemon(timeout=20)
    assert hs is not None
    try:
        assert (isolated_home / "daemon.log.1").read_text() == old
        assert len((isolated_home / "daemon.log").read_bytes()) < len(old)
    finally:
        os.kill(hs["pid"], signal.SIGTERM)
        deadline = time.time() + 10
        while time.time() < deadline and shim._alive(hs):
            time.sleep(0.05)
    assert not shim._alive(hs), "the daemon this test started is gone"


@pytest.fixture(autouse=True)
def _restore_root_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
