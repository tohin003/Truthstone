"""R9 — fail open, but never silently: the daemon says why it is guarding less.

``/health`` lists every reason as ``degraded`` (stable messages) and ``degraded_detail``
(stable codes, plus counts), and the Claude shim's ``--health`` shows each reason once
per session. The case that motivated it (Stage-1 probe ``x_lifecycle.py`` D): a hook with a
stale bearer token gets ``{}`` on every call, exactly like a healthy, quiet session.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from agentguard.adapters import registry
from agentguard.adapters.claude_code import shim
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.daemon import app as daemon_app
from agentguard.daemon import degraded
from tests.conftest import REPO_ROOT, pre_tool_use, user_prompt_submit

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def _clean_registries():
    degraded.REGISTRY.reset()
    registry.reset()
    yield
    degraded.REGISTRY.reset()
    registry.reset()


def make_client(settings: Settings | None = None):
    guard = Guard(settings or Settings())
    return TestClient(daemon_app.create_app(TOKEN, guard.settings, guard)), guard


@pytest.fixture
def client(workspace):
    c, guard = make_client()
    with c:
        yield c
    guard.close()


def reasons(client) -> dict[str, dict]:
    body = client.get("/health").json()
    detail = {item["code"]: item for item in body["degraded_detail"]}
    assert [item["message"] for item in body["degraded_detail"]] == body["degraded"]
    return detail


def stale_hook(client, workspace, headers=None):
    payload = pre_tool_use("Bash", cwd=str(workspace), command="git push --force origin main")
    auth = {"Authorization": "Bearer stale-token-from-an-old-install"} if headers is None else headers
    response = client.post("/hook/claude-code", json=payload, headers=auth)
    assert (response.status_code, response.json()) == (200, {}), "still fails open"


def test_a_healthy_daemon_reports_nothing(client):
    body = client.get("/health").json()
    assert body["degraded"] == [] and body["degraded_detail"] == []


def test_health_reports_recent_auth_failures(client, workspace):
    stale_hook(client, workspace)
    stale_hook(client, workspace, headers={})  # no token at all
    first = reasons(client)["auth_failures"]
    assert first["message"] == daemon_app.AUTH_FAILURES_REASON
    assert (first["count"], first["window_s"]) == (2, 600)
    assert first["last_s_ago"] >= 0
    stale_hook(client, workspace)
    again = reasons(client)["auth_failures"]
    assert again["count"] == 3
    assert again["message"] == first["message"], "the message is stable; the count lives in the detail"


def test_only_silent_rejections_count(client, workspace):
    """/metrics and /shutdown answer 401, which their caller sees; only /hook hides it."""
    assert client.get("/metrics", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/shutdown", headers={"Authorization": "Bearer nope"}).status_code == 401
    auth = {"Authorization": f"Bearer {TOKEN}"}
    good = client.post("/hook/claude-code", json=pre_tool_use(cwd=str(workspace)), headers=auth)
    assert good.status_code == 200
    assert "auth_failures" not in reasons(client)


def test_auth_failures_older_than_the_window_are_forgotten(client, workspace):
    window = client.app.state.auth_failures
    window.note(now=time.monotonic() - daemon_app.AUTH_FAILURE_WINDOW_S - 1)
    assert "auth_failures" not in reasons(client)
    stale_hook(client, workspace)
    assert reasons(client)["auth_failures"]["count"] == 1


def test_a_stale_token_is_logged_once_per_window_not_per_call(client, workspace, caplog):
    with caplog.at_level(logging.WARNING, logger="agentguard.daemon.app"):
        for _ in range(5):
            stale_hook(client, workspace)
    assert len([r for r in caplog.records if "wrong token" in r.getMessage()]) == 1


def test_health_reports_observe_mode(workspace):
    c, guard = make_client(Settings(observe_only=True))
    with c:
        observe = reasons(c)["observe_only"]
    guard.close()
    assert observe["message"] == daemon_app.OBSERVE_ONLY_REASON and "since" in observe


def test_health_reports_what_the_store_says(client, workspace, monkeypatch):
    """The store's ``degraded_reason`` (R1) reaches /health.

    ``ProjectStore.degraded_reason`` is a read-only property over the database's attribute,
    so a degraded database is simulated where it really lives: ``store.db``.
    """
    ws = client.app.state.guard.workspace(workspace)
    assert "store" not in reasons(client), "a healthy store has nothing to say"
    monkeypatch.setattr(ws.store.db, "degraded_reason", "the database is read-only")
    store = reasons(client)["store"]
    assert store["message"] == daemon_app.STORE_REASON.format(reason="the database is read-only")
    monkeypatch.setattr(ws.store.db, "degraded_reason", lambda: "disk nearly full")
    assert "disk nearly full" in reasons(client)["store"]["message"], "a method is called"


def test_a_store_that_cannot_say_does_not_break_health(client, workspace, monkeypatch):
    ws = client.app.state.guard.workspace(workspace)

    def broken():
        raise RuntimeError("store exploded")

    monkeypatch.setattr(ws.store.db, "degraded_reason", broken)
    assert client.get("/health").status_code == 200
    assert "store" not in reasons(client)


def test_other_modules_can_report_reasons(client):
    degraded.report("index-cold", "the index is still building, so evidence checks answer unknown")
    degraded.report("transient", "about to lapse", ttl_s=-1)
    detail = reasons(client)
    assert detail["index-cold"]["message"].startswith("the index is still building")
    assert "transient" not in detail, "expired"
    degraded.clear("index-cold")
    assert reasons(client) == {}


def test_an_adapter_that_cannot_load_is_reported(client, workspace):
    registry.register("test-host", "agentguard.adapters.no_such_host")
    client.post("/hook/test-host", json={}, headers={"Authorization": f"Bearer {TOKEN}"})
    message = reasons(client)["adapter-test-host"]["message"]
    assert message.startswith("the test-host adapter could not be loaded")
    assert "ModuleNotFoundError" in message


def test_health_answers_even_when_the_check_fails(client, monkeypatch):
    def broken(app):
        raise RuntimeError("bug")

    monkeypatch.setattr(daemon_app, "degradation", broken)
    response = client.get("/health")
    assert response.status_code == 200 and response.json()["status"] == "ok"
    assert [item["code"] for item in response.json()["degraded_detail"]] == ["health_check"]


class TestRegistry:
    def test_messages_are_normalised_and_codes_are_refreshed_not_duplicated(self):
        registry_ = degraded.DegradedRegistry()
        registry_.report("x", "  first\nline  ")
        registry_.report("x", "first line", detail={"count": 2})
        (reason,) = registry_.reasons()
        assert (reason.message, reason.detail) == ("first line", {"count": 2})

    def test_a_flood_of_codes_is_capped(self):
        registry_ = degraded.DegradedRegistry(max_reasons=3)
        for n in range(10):
            registry_.report(f"code-{n}", "m")
        assert [r.code for r in registry_.reasons()] == ["code-0", "code-1", "code-2"]

    def test_blank_reports_are_ignored(self):
        registry_ = degraded.DegradedRegistry()
        registry_.report("", "m")
        registry_.report("c", "   ")
        assert registry_.reasons() == []

    def test_recent_events_slide(self):
        window = degraded.RecentEvents(window_s=10)
        assert window.note(now=100.0) == 1
        assert window.note(now=105.0) == 2
        assert window.count(now=110.5) == 1
        assert window.seconds_since_last(now=111.0) == 6.0
        assert window.count(now=200.0) == 0


class TestShimNotices:
    def test_codes_key_the_notice_so_a_new_count_is_not_a_new_notice(self):
        def body(count):
            item = {"code": "auth_failures", "message": daemon_app.AUTH_FAILURES_REASON, "count": count}
            return {"degraded": [item["message"]], "degraded_detail": [item]}

        assert shim.daemon_notices(body(1), "guard") == shim.daemon_notices(body(9), "guard")

    def test_observe_mode_is_said_once_and_only_to_sessions_that_did_not_ask_for_it(self):
        item = {"code": "observe_only", "message": daemon_app.OBSERVE_ONLY_REASON}
        body = {"observing": True, "degraded": [item["message"]], "degraded_detail": [item]}
        assert [kind for kind, _ in shim.daemon_notices(body, "guard")] == ["observe-only"]
        assert shim.daemon_notices(body, "observe") == []

    def test_an_older_daemon_sending_only_messages_is_still_heard(self):
        notices = shim.daemon_notices({"degraded": ["the token is stale"]}, "guard")
        assert [text for _, text in notices] == ["AgentGuard: the token is stale"]

    def test_at_most_five_reasons(self):
        detail = [{"code": f"c{n}", "message": f"reason {n}"} for n in range(8)]
        assert len(shim.daemon_notices({"degraded_detail": detail}, "guard")) == 5


# -- end to end: a real daemon, a stale hook, the shim's --health ---------------------------


def run_health(home, session_id: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, AGENTGUARD_HOME=str(home), PYTHONPATH=str(REPO_ROOT / "src"))
    env.pop("AGENTGUARD_DISABLE", None)
    env.pop("AGENTGUARD_OBSERVE", None)
    return subprocess.run(
        [sys.executable, "-m", "agentguard.adapters.claude_code.shim", "--health"],
        input=json.dumps({**user_prompt_submit("hi"), "session_id": session_id}).encode(),
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_shim_prints_degraded_reasons_once(daemon, workspace):
    payload = pre_tool_use("Bash", cwd=str(workspace), command="git push --force origin main")
    headers = {"Authorization": "Bearer stale-token-from-an-old-install", "Content-Type": "application/json"}
    conn = http.client.HTTPConnection("127.0.0.1", daemon.port, timeout=10)
    try:
        conn.request("POST", "/hook/claude-code", body=json.dumps(payload), headers=headers)
        assert json.loads(conn.getresponse().read()) == {}, "the stale hook is silent"
    finally:
        conn.close()

    first = run_health(daemon.home, "s-stale")
    again = run_health(daemon.home, "s-stale")
    other = run_health(daemon.home, "s-other")

    assert first.returncode == 0 and first.stderr == b""
    lines = json.loads(first.stdout)["systemMessage"].splitlines()
    assert lines == [f"AgentGuard: {daemon_app.AUTH_FAILURES_REASON}"], "one line per reason"
    assert again.stdout == b"", "once per session, not on every prompt"
    assert json.loads(other.stdout)["systemMessage"] == "\n".join(lines), "every session hears it once"
