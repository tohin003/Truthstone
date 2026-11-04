"""Codex's hook-trust fingerprints, reimplemented for tests (codex-rs @ rust-v0.166.0).

Codex skips a non-managed hook until the developer trusts it, and records that trust
against two hashes:

* the **declaration hash** of each hook (``hooks/src/engine/discovery.rs::hook_hash`` +
  ``config/src/fingerprint.rs::version_for_toml``): SHA-256 over the canonical JSON of
  ``{"event_name", "matcher"?, "hooks": [normalized handler]}``;
* for plugin hooks, the **content hash** of the whole plugin directory
  (``hooks/src/engine/plugin_fingerprint.rs``), re-checked on every hook run.

Any change to either one makes every user re-review the hooks. The plugin tests pin both,
so such a change can only be made on purpose. Both functions were checked against the
``currentHash`` values Codex 0.166.0 itself reported (``docs/CODEX.md``).
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any

EVENT_LABELS = {
    "PreToolUse": "pre_tool_use",
    "PermissionRequest": "permission_request",
    "PostToolUse": "post_tool_use",
    "PreCompact": "pre_compact",
    "PostCompact": "post_compact",
    "SessionStart": "session_start",
    "SessionEnd": "session_end",
    "UserPromptSubmit": "user_prompt_submit",
    "SubagentStart": "subagent_start",
    "SubagentStop": "subagent_stop",
    "Stop": "stop",
    "Interrupt": "interrupt",
}
# Events whose matcher Codex honours (lib.rs HOOK_EVENT_NAMES_WITH_MATCHERS); for the rest
# the matcher is dropped before hashing.
MATCHER_EVENTS = {
    "PreToolUse", "PermissionRequest", "PostToolUse", "PreCompact", "PostCompact",
    "SessionStart", "SessionEnd", "SubagentStart", "SubagentStop",
}
CONTEXT_LIMIT_EVENTS = {"PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit", "SubagentStart"}
DEFAULT_CONTEXT_LIMIT = 2500


def declaration_hash(event: str, group: dict[str, Any], handler: dict[str, Any]) -> str:
    timeout = handler.get("timeout")
    if event in ("SessionEnd", "Interrupt"):
        timeout = max(1, min(3, timeout if timeout is not None else 1))
    else:
        timeout = max(1, timeout if timeout is not None else 600)
    normalized: dict[str, Any] = {
        "type": "command",
        "command": handler["command"],
        "timeout": timeout,
        "async": bool(handler.get("async", False)),
    }
    if handler.get("statusMessage") is not None:
        normalized["statusMessage"] = handler["statusMessage"]
    limit = handler.get("additionalContextLimit")
    if event in CONTEXT_LIMIT_EVENTS and limit is not None and limit != DEFAULT_CONTEXT_LIMIT:
        normalized["additionalContextLimit"] = limit
    identity: dict[str, Any] = {"event_name": EVENT_LABELS[event], "hooks": [normalized]}
    matcher = group.get("matcher")
    if event in MATCHER_EVENTS and matcher is not None:
        identity["matcher"] = matcher
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def declaration_hashes(hooks_file: dict[str, Any]) -> dict[str, str]:
    """``{"<event_label>:<group>:<handler>": hash}`` for every handler in a hooks.json."""
    out = {}
    for event, groups in hooks_file["hooks"].items():
        for gi, group in enumerate(groups):
            for hi, handler in enumerate(group["hooks"]):
                out[f"{EVENT_LABELS[event]}:{gi}:{hi}"] = declaration_hash(event, group, handler)
    return out


def plugin_content_hash(root: Path) -> str:
    digest = hashlib.sha256(b"codex-plugin-bundle-v1")
    pending = [root]
    while pending:
        path = pending.pop()
        rel = path.relative_to(root)
        name = rel.name
        if name in ("__pycache__", ".venv") or name.endswith((".pyc", ".egg-info")):
            continue
        encoded = os.fsencode(rel.as_posix()) if rel.parts else b""
        digest.update(struct.pack("<Q", len(encoded)))
        digest.update(encoded)
        if path.is_symlink():
            raise ValueError(f"Codex refuses to fingerprint a symlink: {rel}")
        if path.is_dir():
            digest.update(b"directory")
            pending.extend(sorted(path.iterdir(), key=lambda p: os.fsencode(p.name), reverse=True))
        elif path.is_file():
            data = path.read_bytes()
            digest.update(b"file")
            digest.update(struct.pack("<Q", len(data)))
            digest.update(data)
        else:
            raise ValueError(f"unsupported plugin entry type: {rel}")
    return "sha256:" + digest.hexdigest()
