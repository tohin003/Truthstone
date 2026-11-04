"""Codex sessions hear why the daemon is guarding less, once per reason; `doctor` lists
every reason with its detail (R9).

The Claude shim already told the developer, once per session, about each `/health`
`degraded_detail` reason. The Codex hook's lifecycle path checked only that a daemon
answered and spoke Codex: a stale-token, observe-only or storage-degraded daemon looked
healthy to a Codex session. `doctor` showed at most five reasons, without their detail.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time

import pytest

from tests import codex_schema
from tests.test_doctor import doctor_env, run_doctor  # noqa: F401 - fixture
from truthstone.adapters.codex import hook

HANDSHAKE = {"host": "127.0.0.1", "port": 9, "token": "t", "pid": 4242}
AUTH = (
    "hook requests with a missing or wrong token were rejected in the last 10 minutes, so "
    "whatever sent them is not being guarded."
)
STORE = "its storage is degraded, so what it sees may not be recorded: disk full"


def _health(*reasons: dict, **extra) -> dict:
    return {
        "status": "ok",
        "pid": HANDSHAKE["pid"],
        "enabled": True,
        "observing": False,
        "adapters": ["claude-code", "codex"],
        "degraded": [r["message"] for r in reasons],
        "degraded_detail": list(reasons),
        **extra,
    }


def _run(monkeypatch, capsys, event: str, session: str = "codex-session-1") -> tuple[int, dict]:
    payload = {"hook_event_name": event, "session_id": session, "cwd": "/tmp/ws"}
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    code = hook.main([event])
    out = capsys.readouterr().out
    return code, json.loads(out) if out else {}


@pytest.fixture
def daemon_says(monkeypatch):
    """A live daemon (stubbed) whose /health says whatever the test sets."""
    state = {"health": _health()}
    monkeypatch.setattr(hook, "_lifecycle", lambda: (dict(HANDSHAKE), "", state["health"]))

    def post(hs, body, timeout=0):
        event = json.loads(body)["hook_event_name"]
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": "ctx"}}

    monkeypatch.setattr(hook, "post", post)
    return state


def test_codex_hook_prints_degraded_reasons_once(daemon_says, monkeypatch, capsys):
    daemon_says["health"] = _health(
        {"code": "auth_failures", "message": AUTH, "count": 3, "window_s": 600},
        {"code": "store", "message": STORE},
    )
    code, out = _run(monkeypatch, capsys, "SessionStart")
    assert code == 0
    assert AUTH in out["systemMessage"] and STORE in out["systemMessage"]
    assert out["hookSpecificOutput"]["additionalContext"] == "ctx", "the daemon's answer is kept"
    assert codex_schema.validate(out, "session-start.command.output") == []

    # Same session, same reasons: told already. The count in the detail changing, or the
    # message being reworded, does not make it a new reason: the code is the key.
    daemon_says["health"] = _health(
        {"code": "auth_failures", "message": AUTH + " (reworded)", "count": 9, "window_s": 600},
        {"code": "store", "message": STORE},
    )
    code, out = _run(monkeypatch, capsys, "UserPromptSubmit")
    assert code == 0 and "systemMessage" not in out
    assert out["hookSpecificOutput"]["additionalContext"] == "ctx"

    # A new reason is new.
    daemon_says["health"] = _health(
        {"code": "store", "message": STORE},
        {"code": "index", "message": "the index for /repo is unavailable: too large"},
    )
    _, out = _run(monkeypatch, capsys, "UserPromptSubmit")
    assert out["systemMessage"] == "Truthstone: the index for /repo is unavailable: too large"
    assert codex_schema.validate(out, "user-prompt-submit.command.output") == []

    # Another session hears everything once.
    _, out = _run(monkeypatch, capsys, "SessionStart", session="codex-session-2")
    assert STORE in out["systemMessage"] and "unavailable" in out["systemMessage"]


def test_an_observe_only_or_switched_off_daemon_is_reported_to_codex(daemon_says, monkeypatch, capsys):
    daemon_says["health"] = _health(observing=True)
    _, out = _run(monkeypatch, capsys, "SessionStart")
    assert "OBSERVE-ONLY" in out["systemMessage"]
    daemon_says["health"] = _health(enabled=False)
    _, out = _run(monkeypatch, capsys, "SessionStart", session="codex-session-2")
    assert "switched OFF" in out["systemMessage"]


def test_tool_calls_never_print_notices(daemon_says, monkeypatch, capsys, isolated_home):
    """The hot path stays silent and pays nothing: no /health, no markers."""
    daemon_says["health"] = _health({"code": "store", "message": STORE})
    (isolated_home / "daemon.json").write_text(json.dumps({**HANDSHAKE, "pid": os.getpid()}))
    monkeypatch.setattr(hook, "_health", lambda hs: pytest.fail("/health on the hot path"))
    for event in ("PreToolUse", "PostToolUse", "Stop"):
        _, out = _run(monkeypatch, capsys, event)
        assert "systemMessage" not in out


def test_notices_survive_a_failed_post(daemon_says, monkeypatch, capsys):
    daemon_says["health"] = _health({"code": "store", "message": STORE})

    def broken(*args, **kwargs):
        raise OSError("connection reset")

    monkeypatch.setattr(hook, "post", broken)
    code, out = _run(monkeypatch, capsys, "SessionStart")
    assert code == 0 and out == {"systemMessage": f"Truthstone: {STORE}"}


def test_doctor_lists_degraded_reasons(doctor_env, monkeypatch):  # noqa: F811 - fixture
    import truthstone.adapters.codex.hook as codex_hook
    import truthstone.daemon.app as daemon_app
    from truthstone.core.config import Settings

    home, _, _ = doctor_env
    settings = Settings.load()
    (home / "token").write_text("tok", encoding="utf-8")
    handshake = {"pid": os.getpid(), "host": "127.0.0.1", "port": settings.daemon.port, "token": "tok"}
    since = time.time() - 30
    reasons = [
        {"code": "auth_failures", "message": AUTH, "count": 3, "window_s": 600, "last_s_ago": 12.5},
        {"code": "store", "message": STORE},
        *({"code": f"custom-{n}", "message": f"custom reason {n}", "since": since} for n in range(5)),
    ]
    health = {**_health(*reasons), "pid": os.getpid()}
    monkeypatch.setattr(daemon_app, "daemon_is_alive", lambda: True)
    monkeypatch.setattr(daemon_app, "read_handshake", lambda: dict(handshake))
    monkeypatch.setattr(codex_hook, "_health", lambda hs: dict(health))

    _, output = run_doctor()
    lines = [line for line in output.splitlines() if "degraded: " in line]
    assert len(lines) == len(reasons), "every reason, not the first five"
    auth = next(line for line in lines if "auth_failures" in line)
    assert AUTH in auth and "count=3" in auth and "window_s=600" in auth and "last_s_ago=12.5" in auth
    custom = next(line for line in lines if "custom reason 4" in line)
    assert "code=custom-4" in custom and "since 30s ago" in custom
