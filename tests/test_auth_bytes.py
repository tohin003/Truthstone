"""R16 — the bearer token is compared as bytes.

``secrets.compare_digest`` raises on non-ASCII *strings*, and the server hands headers
over as latin-1 text, so one stray byte in an ``Authorization`` header used to produce a
500 (``x_auth.py`` in the Stage-1 probes). On ``/hook`` that broke fail-open; on
``/metrics`` and ``/shutdown`` it was an unhandled error where a 401 belongs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import pre_tool_use
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.daemon import app as daemon_app

TOKEN = "test-token"

NON_ASCII = [
    b"Bearer \xe9t\xe9",  # latin-1 bytes
    "Bearer tök€n".encode(),  # UTF-8 bytes
    b"Bearer " + TOKEN.encode() + b"\xe9",  # the right token plus one byte
    b"\xff\xfe\x00Bearer",  # garbage, with a NUL
]


@pytest.fixture
def client(workspace, monkeypatch):
    signals = []
    # /shutdown signals its own process; record instead of terminating the test run.
    monkeypatch.setattr(daemon_app.os, "kill", lambda pid, sig: signals.append((pid, sig)))
    guard = Guard(Settings())
    with TestClient(daemon_app.create_app(TOKEN, guard.settings, guard), raise_server_exceptions=False) as c:
        c.signals = signals
        yield c
    guard.close()


@pytest.mark.parametrize("header", NON_ASCII, ids=["latin-1", "utf-8", "token+byte", "garbage"])
def test_non_ascii_auth_fails_open(client, workspace, header):
    auth = {"Authorization": header}
    hook = client.post("/hook/claude-code", json=pre_tool_use(cwd=str(workspace)), headers=auth)
    assert (hook.status_code, hook.json()) == (200, {}), "a hook always fails open"
    assert client.get("/metrics", headers=auth).status_code == 401
    assert client.post("/shutdown", headers=auth).status_code == 401
    assert client.signals == [], "an unauthenticated shutdown must not stop the daemon"


def test_the_right_token_still_works_everywhere(client, workspace):
    auth = {"Authorization": f"Bearer {TOKEN}"}
    hook = client.post(
        "/hook/claude-code",
        json=pre_tool_use("Bash", cwd=str(workspace), command="git push --force origin main"),
        headers=auth,
    )
    assert hook.status_code == 200
    assert client.get("/metrics", headers=auth).status_code == 200
    assert client.post("/shutdown", headers=auth).json() == {"status": "stopping"}
    assert len(client.signals) == 1


def test_a_non_ascii_token_on_the_daemon_side_compares_too(workspace):
    """A hand-edited token file with non-ASCII text must not turn every request into a 500."""
    guard = Guard(Settings())
    token = "tök€n"
    with TestClient(daemon_app.create_app(token, guard.settings, guard), raise_server_exceptions=False) as c:
        assert c.get("/metrics", headers={"Authorization": b"Bearer wrong"}).status_code == 401
        right = f"Bearer {token}".encode()
        # Sent as UTF-8 bytes, read back as latin-1 text: not the same text, so refused, not crashed.
        assert c.get("/metrics", headers={"Authorization": right}).status_code == 401
    guard.close()
