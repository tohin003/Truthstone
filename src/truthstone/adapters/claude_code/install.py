"""Install/uninstall Truthstone's hooks in Claude Code settings (SPEC §26).

This is the *settings-based* install, kept as the fallback for setups that cannot use the
Claude Code plugin (``plugins/truthstone-claude``; see ``docs/CLAUDE-PLUGIN.md``). The two
must never both handle a session: the plugin stands down wherever these hooks are present
(``settings_scan``), and ``truthstone install`` / ``doctor`` say so.

Transport split, and why
------------------------
* ``SessionStart`` is a **command** hook running the shim with ``--ensure-daemon``. It
  fires once per session, so ~50ms of process startup is invisible, and it guarantees the
  daemon is warm before any hot-path hook fires.
* Everything else is an **http** hook straight to the daemon. Claude Code performs the
  request itself, so per-tool-call cost is a localhost round trip instead of a Python
  interpreter start — the difference between meeting and missing SPEC §8.

``PreToolUse``/``PostToolUse`` are matched to tools that can change something: the edit
tools, both shells, and MCP tools. Read/Grep/Glob would short-circuit to ALLOW anyway, so
intercepting them would be pure latency for no signal. ``PostToolUseFailure`` is matched
to the shells: a test run that exits non-zero arrives *only* there, so without it the
completion gate never sees a failing run (G1).

Idempotent: installing twice leaves one copy; uninstalling removes exactly what was added
and nothing a human put there.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

from truthstone.adapters.claude_code import settings_scan
from truthstone.core.config import Settings, get_or_create_token, write_private_text

# Tools that can change something. An anchored regex: unanchored, "Write" would also match
# TodoWrite, and Claude Code treats any matcher with regex characters as a regex.
MUTATING_MATCHER = "^(Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|mcp__.*)$"
# Where a failing command's output arrives (exact-name list, no regex needed).
FAILURE_MATCHER = "Bash|PowerShell"

# Hook timeouts (seconds). Deliberately tight: a wedged daemon must never hold the
# developer hostage, and the fail-open path is cheap.
TIMEOUTS = {
    "SessionStart": 20,
    "Health": 12,
    "UserPromptSubmit": 10,
    "PreToolUse": 5,
    "PostToolUse": 5,
    "PostToolUseFailure": 5,
    "Stop": 10,
    "SessionEnd": 3,
}

# Kept for callers and tests that predate the shared module.
_command_argv = settings_scan.command_argv
_is_ours_hook = settings_scan.is_ours_hook
_is_ours = settings_scan.is_ours_group


def global_settings_path() -> Path:
    """User settings — under ``CLAUDE_CONFIG_DIR`` when Claude Code is configured to use one."""
    return settings_scan.user_settings_path()


def project_settings_path(workspace: Path | None = None) -> Path:
    # settings.local.json is gitignored by Claude Code convention, which matters here
    # because the config carries a local auth token.
    return (workspace or Path.cwd()) / ".claude" / "settings.local.json"


def settings_path(
    project: bool = False, global_: bool = False, workspace: Path | None = None
) -> Path:
    """Resolve an install target, rejecting ambiguous scope flags."""
    if project and global_:
        raise ValueError("choose exactly one of --project or --global")
    return project_settings_path(workspace) if project else global_settings_path()


def _http_hook(url: str, token: str, timeout: int) -> dict[str, Any]:
    return {
        "type": "http",
        "url": url,
        "headers": {
            "Authorization": f"Bearer {token}",
            # Doubles as the ownership marker for _is_ours() and as a label for any
            # human who opens settings.json and wonders what this entry is.
            settings_scan.OWNERSHIP_HEADER: "1",
        },
        "timeout": timeout,
    }


def _command_hook(
    argv: list[str], timeout: int, status_message: str | None = None
) -> dict[str, Any]:
    """Build a Claude Code command hook from argv.

    Claude Code's command-hook schema accepts one shell command string, not a separate
    executable plus an ``args`` array.  ``shlex.join`` keeps paths and other arguments
    correctly quoted while preserving the exact argv we intend to run.
    """
    hook: dict[str, Any] = {
        "type": "command",
        "command": shlex.join(argv),
        "timeout": timeout,
    }
    if status_message is not None:
        hook["statusMessage"] = status_message
    return hook


def _shim_argv(py: str, flag: str) -> list[str]:
    # `-P`: never put the working directory on sys.path. Hooks run inside the developer's
    # repository, and `python -m` would otherwise import a repository file named, say,
    # `json.py` in place of the standard library — code execution by opening a folder.
    return [py, "-P", "-m", settings_scan.SHIM_MODULE, flag]


def build_hook_config(settings: Settings | None = None, python_exe: str | None = None) -> dict[str, Any]:
    settings = settings or Settings.load()
    token = get_or_create_token()
    url = f"{settings.daemon.base_url}/hook/claude-code"
    py = python_exe or sys.executable

    return {
        "SessionStart": [
            {
                "matcher": "startup|resume|clear",
                "hooks": [
                    _command_hook(
                        _shim_argv(py, "--ensure-daemon"),
                        TIMEOUTS["SessionStart"],
                        "Truthstone: warming repository index",
                    )
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    # Health check first: detect a dead daemon, try once to revive it,
                    # and tell the developer if it cannot be. Silent fail-open would
                    # leave them believing they are guarded when they are not.
                    # Once per prompt, not per tool call, so the cost is invisible.
                    _command_hook(_shim_argv(py, "--health"), TIMEOUTS["Health"]),
                    _http_hook(url, token, TIMEOUTS["UserPromptSubmit"]),
                ]
            }
        ],
        "PreToolUse": [
            {"matcher": MUTATING_MATCHER, "hooks": [_http_hook(url, token, TIMEOUTS["PreToolUse"])]}
        ],
        "PostToolUse": [
            {"matcher": MUTATING_MATCHER, "hooks": [_http_hook(url, token, TIMEOUTS["PostToolUse"])]}
        ],
        "PostToolUseFailure": [
            {
                "matcher": FAILURE_MATCHER,
                "hooks": [_http_hook(url, token, TIMEOUTS["PostToolUseFailure"])],
            }
        ],
        "Stop": [{"hooks": [_http_hook(url, token, TIMEOUTS["Stop"])]}],
        "SessionEnd": [{"hooks": [_http_hook(url, token, TIMEOUTS["SessionEnd"])]}],
    }


def _remove_ours_from_group(group: Any) -> Any:
    """Remove only our hooks, preserving a user's hooks in a mixed group.

    Claude groups can contain multiple hook entries. Treating the group as the ownership
    unit would delete an unrelated hook whenever a developer placed it beside ours.
    ``None`` means the group became empty and may be removed by the caller.
    """
    if not isinstance(group, dict):
        return group
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return group
    remaining = [hook for hook in hooks if not _is_ours_hook(hook)]
    if len(remaining) == len(hooks):
        return group
    if not remaining:
        return None
    out = dict(group)
    out["hooks"] = remaining
    return out


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{path} is not valid JSON; refusing to overwrite it ({exc})") from exc
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict[str, Any]) -> None:
    # Truthstone's bearer token is embedded in the HTTP hook headers. Both project-local
    # and global Claude settings are therefore credential-bearing files.
    write_private_text(path, json.dumps(data, indent=2) + "\n")


def merge_hooks(existing: dict[str, Any], new_hooks: dict[str, Any]) -> dict[str, Any]:
    """Add our groups, replacing any previous Truthstone groups, preserving all others."""
    out = dict(existing)
    hooks: dict[str, Any] = dict(out.get("hooks") or {})

    for event, groups in new_hooks.items():
        current = []
        for group in hooks.get(event) or []:
            cleaned = _remove_ours_from_group(group)
            if cleaned is not None:
                current.append(cleaned)
        hooks[event] = current + list(groups)

    out["hooks"] = hooks
    return out


def strip_hooks(existing: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    hooks: dict[str, Any] = dict(out.get("hooks") or {})
    for event in list(hooks):
        remaining = []
        for group in hooks.get(event) or []:
            cleaned = _remove_ours_from_group(group)
            if cleaned is not None:
                remaining.append(cleaned)
        if remaining:
            hooks[event] = remaining
        else:
            hooks.pop(event)
    if hooks:
        out["hooks"] = hooks
    else:
        out.pop("hooks", None)
    return out


def install(
    path: Path, settings: Settings | None = None, dry_run: bool = False, python_exe: str | None = None
) -> tuple[dict[str, Any], bool]:
    """Returns (resulting settings, changed)."""
    existing = _load(path)
    merged = merge_hooks(existing, build_hook_config(settings, python_exe))
    changed = merged != existing
    if changed and not dry_run:
        _save(path, merged)
    return merged, changed


def uninstall(path: Path, dry_run: bool = False) -> tuple[dict[str, Any], bool]:
    existing = _load(path)
    stripped = strip_hooks(existing)
    changed = stripped != existing
    if changed and not dry_run:
        _save(path, stripped)
    return stripped, changed


def is_installed(path: Path) -> bool:
    return settings_scan.hooks_installed(path)
