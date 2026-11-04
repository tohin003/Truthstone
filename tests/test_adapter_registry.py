"""H4 — the adapter registry: names to adapters, imported lazily, registered explicitly,
so that serving a new host never means editing the daemon."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agentguard.adapters import registry
from agentguard.core import hosts
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import EventType
from agentguard.core.events import AgentEvent
from agentguard.daemon.app import create_app

TOKEN = "registry-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _builtin_adapters_only():
    registry.reset()
    yield
    registry.reset()


def fake_adapter(**overrides):
    """A host whose payload is ``{"hook_event_name": ..., "cwd": ...}``, in the core's terms."""

    def to_event(payload):
        if payload.get("hook_event_name") != "Ping":
            return None
        return AgentEvent(event=EventType.USER_PROMPT, agent="test-host", workspace=payload["cwd"],
                          prompt_text="ping")

    def from_decision(event, decision, hook_name):
        return {"heard": hook_name, "action": str(decision.action)}

    return SimpleNamespace(**{"to_event": to_event, "from_decision": from_decision, **overrides})


def ping(client, workspace, event: str = "Ping"):
    payload = {"hook_event_name": event, "cwd": str(workspace)}
    return client.post("/hook/test-host", json=payload, headers=AUTH)


@pytest.fixture
def client(workspace):
    guard = Guard(Settings())
    with TestClient(create_app(TOKEN, guard.settings, guard)) as c:
        yield c
    guard.close()


def test_the_built_in_hosts_are_registered():
    assert registry.names() == ["claude-code", "codex"]
    assert registry.available() == ["claude-code", "codex"]
    assert registry.load_errors() == {}


def test_a_registered_adapter_satisfies_the_core_protocol():
    claude, codex = registry.get("claude-code"), registry.get("codex")
    assert isinstance(claude, hosts.Adapter) and isinstance(codex, hosts.Adapter)
    assert claude.name == "claude-code" and claude.handle_payload is None
    assert callable(codex.handle_payload), "Codex combines a multi-file patch itself"
    assert registry.get("codex") is codex, "loaded once, then cached"


def test_the_hook_name_comes_from_the_payload_unless_the_adapter_says_otherwise():
    assert registry.get("claude-code").hook_name({"hook_event_name": "Stop"}) == "Stop"
    assert registry.get("claude-code").hook_name({"hook_event_name": 7}) == ""
    registry.register("test-host", fake_adapter(hook_name=lambda payload: payload["event"]))
    assert registry.get("test-host").hook_name({"event": "Ping"}) == "Ping"


def test_registration_is_lazy(monkeypatch):
    imported = []

    def import_module(name):
        imported.append(name)
        return fake_adapter()

    monkeypatch.setattr(registry.importlib, "import_module", import_module)
    registry.register("test-host", "some_package.test_host.translate")
    assert imported == [] and "test-host" in registry.names()
    assert registry.get("test-host") is not None
    assert registry.get("test-host") is not None
    assert imported == ["some_package.test_host.translate"], "imported on first use, once"


def test_unknown_names_are_absent():
    assert registry.get("cursor") is None
    assert registry.get(None) is None


@pytest.mark.parametrize("name", ["", "Cursor", "../codex", "a b", "x" * 65, "-lead"])
def test_names_must_be_route_segments(name):
    with pytest.raises(ValueError):
        registry.register(name, fake_adapter())


def test_a_name_is_registered_once_unless_replaced():
    with pytest.raises(ValueError):
        registry.register("codex", fake_adapter())
    replacement = fake_adapter()
    registry.register("codex", replacement, replace=True)
    assert registry.get("codex").impl is replacement


def test_an_adapter_that_cannot_load_is_absent_and_says_why(caplog):
    registry.register("test-host", "agentguard.adapters.no_such_host")
    with caplog.at_level(logging.ERROR, logger="agentguard.adapters.registry"):
        assert registry.get("test-host") is None
        assert registry.get("test-host") is None
    assert len([r for r in caplog.records if "test-host" in r.getMessage()]) == 1, "logged once"
    assert registry.load_errors()["test-host"].startswith("ModuleNotFoundError")
    assert "test-host" not in registry.available()
    registry.register("test-host", fake_adapter(), replace=True)
    assert registry.get("test-host") is not None and registry.load_errors() == {}


def test_something_that_is_not_an_adapter_is_refused():
    registry.register("test-host", SimpleNamespace(to_event=lambda payload: None))
    assert registry.get("test-host") is None
    assert "from_decision" in registry.load_errors()["test-host"]


def test_the_daemon_serves_a_newly_registered_host_without_being_edited(client, workspace):
    registry.register("test-host", fake_adapter())
    assert "test-host" in client.get("/health").json()["adapters"]
    response = ping(client, workspace)
    assert response.json() == {"heard": "Ping", "action": "allow"}
    ignored = ping(client, workspace, "Other")
    assert ignored.json() == {}


def test_the_daemon_prefers_handle_payload(client, workspace):
    seen = []

    def handle_payload(guard, payload):
        seen.append(payload["hook_event_name"])
        return {"combined": True}

    registry.register("test-host", fake_adapter(handle_payload=handle_payload))
    response = ping(client, workspace)
    assert response.json() == {"combined": True} and seen == ["Ping"]


def test_a_broken_or_misbehaving_adapter_fails_open(client, workspace):
    registry.register("test-host", "agentguard.adapters.no_such_host")
    assert "test-host" not in client.get("/health").json()["adapters"]
    response = ping(client, workspace)
    assert (response.status_code, response.json()) == (200, {})

    def explodes(event, decision, hook_name):
        raise RuntimeError("adapter bug")

    registry.register("test-host", fake_adapter(from_decision=explodes), replace=True)
    response = ping(client, workspace)
    assert (response.status_code, response.json()) == (200, {})

    not_an_object = fake_adapter(from_decision=lambda event, decision, hook_name: ["a", "list"])
    registry.register("test-host", not_an_object, replace=True)
    response = ping(client, workspace)
    assert (response.status_code, response.json()) == (200, {})
