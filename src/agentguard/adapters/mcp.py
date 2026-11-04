"""MCP tool calls, classified for the core (``IMPROVEMENTS.md`` H5, adapter half).

Both hosts name a server's tool ``mcp__<server>__<tool>`` in their hooks (Claude Code
2.1.92; Codex 0.166.0 keeps "standard MCP identifiers such as ``mcp__server__tool``", read
from its binary). Whether such a tool can change the workspace is something only the tool's
own MCP annotations (``readOnlyHint``, ``destructiveHint``) say, and the MCP specification
is explicit that a client must not make decisions on annotations from a server it does not
trust. So the order is:

1. **Trusted annotations.** Neither host hands any annotation to a hook, trusted or not:

   * Claude Code 2.1.92 — the PreToolUse input is the common hook fields (``session_id``,
     ``transcript_path``, ``cwd``, ``permission_mode``, ``agent_id``, ``agent_type``) plus
     ``hook_event_name``, ``tool_name``, ``tool_input`` and ``tool_use_id`` (the hook-input
     schema and the ``executePreToolHooks`` builder in ``cli.js``). The MCP wrapper reads
     ``annotations.readOnlyHint`` only internally (``isReadOnly()``), for its own
     permission logic;
   * Codex 0.166.0 — the PreToolUse input schema (``tests/fixtures/codex_schemas``) is
     closed, ``additionalProperties: false``, with no annotation field.

   A field in a payload that claimed to carry one would at best be the server describing
   itself, so none is read.
2. **Adapter hints from configuration.** AgentGuard has none (no tool-hint setting in
   ``core/config.py``); adding one is a core change.
3. **Otherwise unknown.** An unknown tool is never read-only: it goes through the core like
   any other action, and its name — however much it sounds like a read
   (``mcp__fs__read_file``) — proves nothing.

What *is* known read-only: each host's own tools for reading MCP resources. They belong to
the host, not to a server, and they are read-only by construction — Claude Code marks both
``isReadOnly(){return!0}`` in ``cli.js``; Codex implements its three in
``core/src/tools/handlers/mcp_resource/``. A server cannot spoof them: every server tool
carries the ``mcp__`` prefix on both hosts.

The result goes through the H5 seam only: ``AgentEvent.host_hints["read_only"] = True`` for
a known read-only tool, and nothing at all otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MCP_PREFIX = "mcp__"

Effect = Literal["read_only", "unknown"]

# Each host's own MCP-resource readers, by the host's adapter name (``AgentEvent.agent``).
HOST_READ_ONLY_TOOLS: dict[str, frozenset[str]] = {
    # cli.js 2.1.92: `ListMcpResourcesTool` and `ReadMcpResourceTool`, both isReadOnly.
    "claude-code": frozenset({"ListMcpResourcesTool", "ReadMcpResourceTool"}),
    # codex 0.166.0: core/src/tools/handlers/mcp_resource/{list_mcp_resources,
    # list_mcp_resource_templates,read_mcp_resource}.rs
    "codex": frozenset({"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}),
}


@dataclass(frozen=True, slots=True)
class McpTool:
    """A server's tool, from its hook name: ``mcp__<server>__<tool>``."""

    server: str
    tool: str


def parse(name: Any) -> McpTool | None:
    """The server and tool of an ``mcp__<server>__<tool>`` name; None for anything else."""
    if not isinstance(name, str) or not name.startswith(MCP_PREFIX):
        return None
    server, sep, tool = name[len(MCP_PREFIX) :].partition("__")
    if not (server and sep and tool):
        return None
    return McpTool(server, tool)


def effect(host: str, tool_name: Any) -> Effect | None:
    """``read_only`` for a tool known to be read-only, ``unknown`` for any other MCP tool,
    ``None`` for a tool that is not an MCP tool (the core's own vocabulary covers those)."""
    if not isinstance(tool_name, str):
        return None
    if tool_name in HOST_READ_ONLY_TOOLS.get(host, frozenset()):
        return "read_only"
    if parse(tool_name) is not None:
        return "unknown"
    return None


def host_hints(host: str, tool_name: Any) -> dict[str, Any]:
    """The H5 hints for one tool call: ``{"read_only": True}`` only when it is known."""
    return {"read_only": True} if effect(host, tool_name) == "read_only" else {}
