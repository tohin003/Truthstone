"""Install/uninstall AgentGuard's hooks in Codex's ``hooks.json``.

Two ways to attach AgentGuard to Codex share the hook *specification* below and differ
only in the command each hook runs:

* ``agentguard install codex`` writes ``~/.codex/hooks.json`` (``--global``, honouring
  ``CODEX_HOME``) or ``<repo>/.codex/hooks.json`` (``--project``) with commands that run
  this interpreter's ``agentguard.adapters.codex.hook``;
* the Codex plugin (``plugins/agentguard``) ships the same hooks, pointed at a small
  launcher that finds the runtime (``plugin.py`` generates both from ``HOOK_SPECS``).

``hooks.json`` rather than inline ``[hooks]`` in ``config.toml``: it is JSON, so it can be
merged without a TOML writer, and Codex reads both. Codex warns at startup if one layer
has both; a user who already keeps inline TOML hooks should use the plugin instead.

Codex skips hooks it has not been told to trust. Installing never pretends otherwise and
never writes trust on the user's behalf: approving hooks is the developer's decision, made
in Codex's ``/hooks`` review (``agentguard doctor`` reports which hooks still need it).

Idempotent, and reversible exactly: AgentGuard's entries are recognised by the command they
run, nothing else in the file is touched, and ``uninstall`` removes only those entries.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentguard import names
from agentguard.core.config import write_private_text

HOOK_MODULE = "agentguard.adapters.codex.hook"
# Codex tool names worth intercepting. `apply_patch` is Codex's only file-editing tool
# (it also answers to the matcher aliases Write/Edit); everything else either cannot
# change the workspace or is not AgentGuard's to judge.
TOOL_MATCHER = "Bash|apply_patch"

HOOKS_FILE_DESCRIPTION = (
    "Codex lifecycle hooks. Entries that run agentguard.adapters.codex.hook are managed by "
    "`agentguard install codex`; everything else here is yours and is left alone."
)


@dataclass(frozen=True, slots=True)
class HookSpec:
    """One AgentGuard hook: which Codex event, how it is invoked, how long it may take."""

    event: str  # Codex event name
    arg: str  # the forwarder's event argument
    timeout: int  # seconds; Codex's default would be 600
    matcher: str | None = None
    status_message: str | None = None


# Deliberately bounded timeouts: a wedged daemon must never hold the developer hostage,
# and the forwarder gives up well before Codex would kill it. SessionStart is generous
# because it may have to start the daemon and, for the plugin, install the runtime once.
HOOK_SPECS: tuple[HookSpec, ...] = (
    HookSpec("SessionStart", "session-start", 60, status_message="AgentGuard: starting the local guard"),
    HookSpec("UserPromptSubmit", "user-prompt-submit", 30),
    HookSpec("PreToolUse", "pre-tool-use", 10, matcher=TOOL_MATCHER),
    HookSpec("PostToolUse", "post-tool-use", 10, matcher=TOOL_MATCHER),
    HookSpec("Stop", "stop", 30),
    HookSpec("SessionEnd", "session-end", 3),  # Codex caps SessionEnd at 3 s
)
HOOK_ARGS = frozenset(spec.arg for spec in HOOK_SPECS)


def build_hooks(command_for: Any) -> dict[str, list[dict[str, Any]]]:
    """``{event: [matcher group]}`` for every spec, using ``command_for(spec) -> str``."""
    hooks: dict[str, list[dict[str, Any]]] = {}
    for spec in HOOK_SPECS:
        handler: dict[str, Any] = {"type": "command", "command": command_for(spec), "timeout": spec.timeout}
        if spec.status_message:
            handler["statusMessage"] = spec.status_message
        group: dict[str, Any] = {}
        if spec.matcher:
            group["matcher"] = spec.matcher
        group["hooks"] = [handler]
        hooks.setdefault(spec.event, []).append(group)
    return hooks


def build_hook_config(python_exe: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """The hooks ``agentguard install codex`` writes: this interpreter, this package."""
    py = python_exe or sys.executable
    # `-P`: Codex runs hooks in the session's directory, i.e. the developer's repository, and
    # `python -m` would put it first on sys.path, so a repository file such as `json.py` could
    # shadow a module the hook imports. Ownership detection matches the trailing
    # `-m <module> <arg>`, so entries written without `-P` are still recognised and upgraded.
    return build_hooks(lambda spec: shlex.join([py, "-P", "-m", HOOK_MODULE, spec.arg]))


# -- locations ----------------------------------------------------------------------


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def global_hooks_path() -> Path:
    return codex_home() / "hooks.json"


def project_hooks_path(workspace: Path | None = None) -> Path:
    # Codex loads a project's `.codex/` layer only once the project is trusted.
    return (workspace or Path.cwd()) / ".codex" / "hooks.json"


def hooks_path(project: bool = False, global_: bool = False, workspace: Path | None = None) -> Path:
    if project and global_:
        raise ValueError("choose exactly one of --project or --global")
    return project_hooks_path(workspace) if project else global_hooks_path()


# -- ownership ----------------------------------------------------------------------


def _is_ours_hook(hook: Any) -> bool:
    """An AgentGuard entry runs our forwarder module with one of our event arguments.

    Matched on the parsed argv, never on a substring: a user's own hook that merely
    mentions "agentguard" is not ours to remove. Entries written under a former product
    name are ours too (`names.variants`), so a reinstall replaces them.
    """
    if not isinstance(hook, dict) or hook.get("type") != "command":
        return False
    command = hook.get("command")
    if not isinstance(command, str):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    return (
        len(argv) >= 4
        and argv[-3] == "-m"
        and argv[-2] in names.variants(HOOK_MODULE)
        and argv[-1] in HOOK_ARGS
    )


def _remove_ours_from_group(group: Any) -> Any:
    """Drop our handlers from a matcher group; None if the group is left empty."""
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


def _clean(groups: Any) -> list[Any]:
    out = []
    for group in groups if isinstance(groups, list) else []:
        cleaned = _remove_ours_from_group(group)
        if cleaned is not None:
            out.append(cleaned)
    return out


def merge_hooks(existing: dict[str, Any], new_hooks: dict[str, Any]) -> dict[str, Any]:
    """Add our groups (replacing any older copies of them), preserving everything else."""
    out = dict(existing)
    hooks: dict[str, Any] = dict(out.get("hooks") or {})
    for event, groups in new_hooks.items():
        hooks[event] = _clean(hooks.get(event)) + list(groups)
    out["hooks"] = hooks
    if out.get("description") in names.variants(HOOKS_FILE_DESCRIPTION):
        out["description"] = HOOKS_FILE_DESCRIPTION  # ours, possibly written under a former name
    out.setdefault("description", HOOKS_FILE_DESCRIPTION)
    return out


def strip_hooks(existing: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    hooks: dict[str, Any] = dict(out.get("hooks") or {})
    for event in list(hooks):
        remaining = _clean(hooks[event])
        if remaining:
            hooks[event] = remaining
        else:
            hooks.pop(event)
    out["hooks"] = hooks
    return out


# -- file I/O -----------------------------------------------------------------------


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"{path} is not valid JSON; refusing to overwrite it ({exc})") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} is not a JSON object; refusing to overwrite it")
    return data


def _save(path: Path, data: dict[str, Any]) -> None:
    # No credential lives here (the forwarder reads the daemon handshake), but an atomic,
    # symlink-refusing write is the right way to edit a file another program reads.
    write_private_text(path, json.dumps(data, indent=2) + "\n")


def install(path: Path, dry_run: bool = False, python_exe: str | None = None) -> tuple[dict[str, Any], bool]:
    """Returns (resulting hooks.json document, changed)."""
    existing = _load(path)
    merged = merge_hooks(existing, build_hook_config(python_exe))
    changed = merged != existing
    if changed and not dry_run:
        _save(path, merged)
    return merged, changed


def uninstall(path: Path, dry_run: bool = False) -> tuple[dict[str, Any], bool]:
    """Remove our entries. A file that only ever held them is removed entirely."""
    existing = _load(path)
    if not existing:
        return existing, False
    stripped = strip_hooks(existing)
    changed = stripped != existing
    if changed and not dry_run:
        if not stripped["hooks"] and set(stripped) <= {"description", "hooks"} and stripped.get(
            "description", HOOKS_FILE_DESCRIPTION
        ) in names.variants(HOOKS_FILE_DESCRIPTION):
            path.unlink(missing_ok=True)
        else:
            _save(path, stripped)
    return stripped, changed


def is_installed(path: Path) -> bool:
    try:
        hooks = (_load(path).get("hooks") or {}).values()
    except RuntimeError:
        return False
    return any(
        _is_ours_hook(hook)
        for groups in hooks
        if isinstance(groups, list)
        for group in groups
        if isinstance(group, dict)
        for hook in (group.get("hooks") if isinstance(group.get("hooks"), list) else [])
    )
