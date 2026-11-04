"""H4 — every registered host honours the adapter contract on its own captured payloads.

For each adapter in the registry that has captured payloads (``fixtures/hosts/README.md``
says where they live), every payload goes through the same steps the daemon takes:

* ``to_event`` succeeds (an event, or ``None`` for a payload the core should not see);
* a real ``Guard`` over a copy of ``fixtures/pyrepo`` returns a ``Decision``;
* ``from_decision`` (or ``handle_payload``) returns a JSON object that never says "defer"
  and never grants: no bare ``allow``, no ``approve``.

Then every DecisionAction, with and without sign-off, is rendered for every captured
event, and the same payloads are sent through the daemon's real ``/hook/<name>`` route.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agentguard.adapters import registry
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import ChallengeCategory, DecisionAction, FailureMode, Severity, Verdict
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision, Finding
from agentguard.daemon.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"
# Hosts captured before fixtures/hosts/ existed keep their original directories.
FIXTURE_DIRS = {
    "claude-code": FIXTURES / "hook_payloads",
    "codex": FIXTURES / "codex_payloads",
}
# The scrubbed workspace path in every captured payload.
CAPTURED_ROOT = "/workspace"
LIFECYCLE = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
             "SubagentStop", "Stop", "SessionEnd"]
TOKEN = "contract-token"


def fixture_dir(host: str) -> Path:
    return FIXTURE_DIRS.get(host, FIXTURES / "hosts" / host)


def payloads(host: str) -> list[Path]:
    def order(path: Path) -> tuple[int, str]:
        name = json.loads(path.read_text(encoding="utf-8")).get("hook_event_name", "")
        return (LIFECYCLE.index(name) if name in LIFECYCLE else len(LIFECYCLE), path.name)

    return sorted(fixture_dir(host).glob("*.json"), key=order)


def hosts_with_fixtures() -> list[str]:
    return [host for host in registry.names() if payloads(host)]


def localise(value: Any, workspace: str) -> Any:
    """Point a captured payload at this test's workspace instead of the scrubbed one."""
    if isinstance(value, str):
        return value.replace(CAPTURED_ROOT, workspace)
    if isinstance(value, list):
        return [localise(item, workspace) for item in value]
    if isinstance(value, dict):
        return {key: localise(item, workspace) for key, item in value.items()}
    return value


def grants_or_defers(out: Any) -> list[str]:
    """Every place in a hook output that would defer or grant a permission."""
    problems: list[str] = []
    if isinstance(out, dict):
        if out.get("permissionDecision") == "allow" and "updatedInput" not in out:
            problems.append("bare permissionDecision: allow")
        if out.get("decision") in ("allow", "approve"):
            problems.append(f"decision: {out['decision']}")
        for value in out.values():
            problems.extend(grants_or_defers(value))
    elif isinstance(out, list):
        for value in out:
            problems.extend(grants_or_defers(value))
    elif out == "defer":
        problems.append("defer")
    return problems


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


@pytest.fixture(autouse=True)
def _builtin_adapters_only():
    registry.reset()
    yield
    registry.reset()


def test_the_built_in_hosts_have_contract_fixtures():
    assert {"claude-code", "codex"} <= set(hosts_with_fixtures())


def test_every_registered_host_has_contract_fixtures():
    """Captured payloads are the evidence of a host's contract: a host without them is
    a host nobody has verified."""
    assert [host for host in registry.names() if not payloads(host)] == []


@pytest.mark.parametrize("host", ["claude-code", "codex"])
def test_every_captured_payload_honours_the_contract(host, guard, repo):
    adapter = registry.get(host)
    assert adapter is not None
    translated = 0
    for path in payloads(host):
        payload = localise(json.loads(path.read_text(encoding="utf-8")), str(repo))
        event = adapter.to_event(dict(payload))
        assert event is None or isinstance(event, AgentEvent), path.name
        if event is not None:
            translated += 1
            assert isinstance(guard.handle(event), Decision), path.name
        if adapter.handle_payload is not None:
            out = adapter.handle_payload(guard, dict(payload))
        elif event is not None:
            out = adapter.from_decision(event, guard.handle(event), adapter.hook_name(payload))
        else:
            out = {}
        assert isinstance(out, dict), path.name
        json.dumps(out)
        assert grants_or_defers(out) == [], (path.name, out)
    assert translated, f"none of {host}'s payloads reached the core"


RISK = Finding(
    category=ChallengeCategory.RISK,
    verdict=Verdict.REQUIRES_HUMAN,
    failure_mode=FailureMode.DESTRUCTIVE_ACTION,
    severity=Severity.HIGH,
    subject="git push --force",
    summary="Irreversible command: force push",
)


def every_decision() -> list[Decision]:
    return [
        Decision(
            action=action,
            reason="AgentGuard — evidence check\n\nThe evidence.",
            additional_context="Extra context.",
            updated_arguments={"command": "ls"},
            signoff_required=signoff,
            findings=[RISK] if signoff else [],
        )
        for action in DecisionAction
        for signoff in (False, True)
    ]


@pytest.mark.parametrize("host", ["claude-code", "codex"])
def test_every_action_on_every_captured_event_honours_the_contract(host, repo):
    adapter = registry.get(host)
    for path in payloads(host):
        payload = localise(json.loads(path.read_text(encoding="utf-8")), str(repo))
        event = adapter.to_event(dict(payload))
        if event is None:
            continue
        for decision in every_decision():
            out = adapter.from_decision(event, decision, adapter.hook_name(payload))
            assert isinstance(out, dict)
            assert grants_or_defers(out) == [], (path.name, decision.action, out)


@pytest.mark.parametrize("host", ["claude-code", "codex"])
def test_the_daemon_routes_each_host_through_the_registry(host, guard, repo):
    app = create_app(TOKEN, guard.settings, guard)
    with TestClient(app) as client:
        assert host in client.get("/health").json()["adapters"]
        for path in payloads(host):
            payload = localise(json.loads(path.read_text(encoding="utf-8")), str(repo))
            headers = {"Authorization": f"Bearer {TOKEN}"}
            response = client.post(f"/hook/{host}", json=payload, headers=headers)
            assert response.status_code == 200, path.name
            body = response.json()
            assert isinstance(body, dict) and grants_or_defers(body) == [], (path.name, body)
