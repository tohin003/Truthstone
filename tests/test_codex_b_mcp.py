"""H5 (adapter half): MCP tool calls are classified, and only a known read is read-only.

What the hosts actually send, verified rather than assumed (``adapters/mcp.py`` has the
sources): no hook payload on either host carries MCP annotations, and Truthstone has no
tool-hint configuration. So a server's ``mcp__<server>__<tool>`` is *unknown* on both
hosts, whatever its name suggests; the only MCP tools known to be read-only are each
host's own resource readers. Read-only reaches the core through the H5 seam,
``host_hints["read_only"]``, and makes it skip evidence and scope (indeed all validation).
"""

from __future__ import annotations

import json
import random
import shutil
import string
import subprocess
from pathlib import Path

import pytest

from tests.codex_schema import validate
from truthstone import evidence
from truthstone.adapters import mcp
from truthstone.adapters.claude_code import translate as claude
from truthstone.adapters.codex import translate as codex
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction
from truthstone.validate import checks

FIXTURES = Path(__file__).parent / "fixtures"
CLAUDE_READERS = ["ListMcpResourcesTool", "ReadMcpResourceTool"]
CODEX_READERS = ["list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"]
UNKNOWN = ["mcp__fs__read_file", "mcp__github__get_issue", "mcp__fs__write_file", "mcp__db__query"]


# -- what the payloads carry ------------------------------------------------------------


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def test_no_captured_payload_carries_tool_annotations():
    for directory in ("hook_payloads", "codex_payloads"):
        for path in sorted((FIXTURES / directory).glob("*.json")):
            keys = _keys(json.loads(path.read_text(encoding="utf-8")))
            assert not {k for k in keys if "annotation" in k.lower() or k.endswith("Hint")}, path.name


def test_codex_cannot_send_an_annotation_in_a_pre_tool_payload():
    """Codex 0.166.0's PreToolUse input schema is closed: no field for annotations."""
    payload = json.loads((FIXTURES / "codex_payloads" / "PreToolUse.Bash.json").read_text())
    assert validate(payload, "pre-tool-use.command.input") == []
    payload["tool_annotations"] = {"readOnlyHint": True}
    assert validate(payload, "pre-tool-use.command.input") != []


# -- the classifier ----------------------------------------------------------------------


def test_mcp_names_are_parsed_into_server_and_tool():
    assert mcp.parse("mcp__github__get_issue") == mcp.McpTool("github", "get_issue")
    assert mcp.parse("mcp__ide__get__diagnostics") == mcp.McpTool("ide", "get__diagnostics")
    for name in ("mcp__", "mcp__github", "mcp____x", "mcp__x__", "Bash", "", None, 7, ["mcp__a__b"]):
        assert mcp.parse(name) is None, name


@pytest.mark.parametrize(("host", "tools"), [("claude-code", CLAUDE_READERS), ("codex", CODEX_READERS)])
def test_each_hosts_own_resource_readers_are_read_only(host, tools):
    for tool in tools:
        assert mcp.effect(host, tool) == "read_only"
        assert mcp.host_hints(host, tool) == {"read_only": True}


@pytest.mark.parametrize("host", ["claude-code", "codex"])
def test_a_servers_tool_is_unknown_whatever_its_name_says(host):
    spoofs = [f"mcp__evil__{tool}" for tool in CLAUDE_READERS + CODEX_READERS]
    for tool in UNKNOWN + spoofs:
        assert mcp.effect(host, tool) == "unknown", tool
        assert mcp.host_hints(host, tool) == {}, tool


def test_a_reader_of_one_host_is_nothing_special_on_the_other():
    assert mcp.effect("codex", "ReadMcpResourceTool") is None
    assert mcp.effect("claude-code", "read_mcp_resource") is None
    assert mcp.host_hints("cursor", "ReadMcpResourceTool") == {}


def test_no_other_name_is_ever_read_only():
    """Seeded fuzz: only the exact host readers are read-only, nothing else, ever."""
    rng = random.Random(20261104)
    alphabet = string.ascii_letters + string.digits + "_-."
    readers = {(host, tool) for host, tools in mcp.HOST_READ_ONLY_TOOLS.items() for tool in tools}
    for _ in range(5000):
        name = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        if rng.random() < 0.5:
            name = "mcp__" + name
        for host in ("claude-code", "codex", "other"):
            if (host, name) not in readers:
                assert mcp.host_hints(host, name) == {}, (host, name)


# -- through a real Guard -------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=dest, check=True)
    subprocess.run([*git, "add", "-A"], cwd=dest, check=True)
    subprocess.run([*git, "commit", "-qm", "init"], cwd=dest, check=True)
    return dest


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


@pytest.fixture
def calls(monkeypatch) -> dict[str, int]:
    """How often the evidence and scope checks ran."""
    seen = {"evidence": 0, "scope": 0}
    real_evidence, real_scope = evidence.check, checks.scope_creep

    def counted_evidence(*args, **kwargs):
        seen["evidence"] += 1
        return real_evidence(*args, **kwargs)

    def counted_scope(*args, **kwargs):
        seen["scope"] += 1
        return real_scope(*args, **kwargs)

    monkeypatch.setattr(evidence, "check", counted_evidence)
    monkeypatch.setattr(checks, "scope_creep", counted_scope)
    return seen


def claude_payload(repo: Path, hook: str, tool: str, tool_input: dict, **extra) -> dict:
    return {
        "session_id": "sess-mcp",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": str(repo),
        "permission_mode": "default",
        "hook_event_name": hook,
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_use_id": "toolu_mcp",
        **extra,
    }


def codex_payload(repo: Path, hook: str, tool: str, tool_input: dict, **extra) -> dict:
    return {
        "session_id": "sess-mcp",
        "turn_id": "turn-1",
        "transcript_path": None,
        "cwd": str(repo),
        "hook_event_name": hook,
        "model": "gpt-test",
        "permission_mode": "default",
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_use_id": "call-mcp",
        **extra,
    }


def prompt(guard, repo: Path) -> None:
    payload = claude_payload(repo, "UserPromptSubmit", "", {}, prompt="Rename the users endpoint")
    guard.handle(claude.to_event(payload))


@pytest.mark.parametrize("tool", CLAUDE_READERS)
def test_claude_an_mcp_read_only_tool_skips_evidence_and_scope(guard, repo, calls, tool):
    prompt(guard, repo)
    uri = f"file://{repo}/src/shop/models.py"
    event = claude.to_event(claude_payload(repo, "PreToolUse", tool, {"server": "fs", "uri": uri}))
    assert event.is_read_only and not event.is_mutating
    decision = guard.handle(event)
    assert decision.action is DecisionAction.ALLOW
    assert calls == {"evidence": 0, "scope": 0}
    assert claude.from_decision(event, decision, "PreToolUse") == {}


@pytest.mark.parametrize("tool", UNKNOWN)
def test_claude_an_unknown_mcp_tool_is_not_read_only(guard, repo, calls, tool):
    prompt(guard, repo)
    tool_input = {"file_path": f"{repo}/src/shop/models.py", "content": "x = 1\n"}
    event = claude.to_event(claude_payload(repo, "PreToolUse", tool, tool_input))
    assert not event.is_read_only
    assert "read_only" not in event.host_hints
    guard.handle(event)
    assert calls["evidence"] == 1  # it went through the validator like any other action


def test_claude_payload_borne_annotations_are_not_trusted(repo):
    payload = claude_payload(
        repo,
        "PreToolUse",
        "mcp__fs__write_file",
        {"path": "x", "annotations": {"readOnlyHint": True}},
        tool_annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    event = claude.to_event(payload)
    assert not event.is_read_only and event.host_hints == {}


def test_codex_an_mcp_read_only_tool_skips_evidence_and_scope(guard, repo, calls):
    codex.handle_payload(guard, codex_payload(repo, "UserPromptSubmit", "", {}, prompt="Read the docs"))
    payload = codex_payload(repo, "PreToolUse", "read_mcp_resource", {"server": "docs", "uri": "docs://a"})
    (event,) = codex.to_events(payload)
    assert event.is_read_only and event.host_hints == {"read_only": True}
    decision = guard.handle(event)
    assert decision.action is DecisionAction.ALLOW
    assert calls == {"evidence": 0, "scope": 0}
    out = codex.handle_payload(guard, payload)
    assert out == {} and validate(out, "pre-tool-use.command.output") == []
    post = dict(payload, hook_event_name="PostToolUse", tool_response={"contents": []})
    (recorded,) = codex.to_events(post)
    assert recorded.is_read_only and recorded.result == {"contents": []}


@pytest.mark.parametrize("tool", UNKNOWN)
def test_codex_an_unknown_mcp_tool_is_not_read_only(repo, tool):
    tool_input = {"file_path": f"{repo}/src/shop/models.py", "content": "x = 1\n"}
    assert codex.to_events(codex_payload(repo, "PreToolUse", tool, tool_input)) == []  # never judged
    post = codex_payload(repo, "PostToolUse", tool, tool_input, tool_response="ok")
    (event,) = codex.to_events(post)
    assert not event.is_read_only and event.host_hints == {}
    assert event.arg("file_path") is None  # never mistaken for an edit


def test_the_core_list_misses_claudes_own_resource_readers():
    """``core/events.py`` READ_ONLY_TOOLS says "ListMcpResources"; Claude Code 2.1.92 calls
    it ``ListMcpResourcesTool`` and also has ``ReadMcpResourceTool``. The adapter's hint
    covers both until the core list is fixed (reported: core/events.py has no owner)."""
    from truthstone.core.events import READ_ONLY_TOOLS

    assert not set(CLAUDE_READERS) <= READ_ONLY_TOOLS
