"""Find AgentGuard in Claude Code's configuration: settings-based hooks, and the plugin.

AgentGuard can reach Claude Code two ways — hooks it writes into a ``settings.json``
(``agentguard install claude``), or the Claude Code plugin. With both active, every event
would be handled twice: each tool call judged twice, each challenge rationed twice, the
completion gate's per-task budget spent twice. This module is how each side notices the
other:

* the plugin's SessionStart (``plugin.py``) checks the settings files Claude Code reads
  for the session and stands down where settings hooks already cover it;
* ``agentguard install`` and ``agentguard doctor`` check the plugin's install records.

Stdlib-only: the plugin runs this in a hook process and must not import pydantic.
``install.py`` uses the same ownership test, so there is exactly one definition of
"this hook is AgentGuard's".
"""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The plugin's name in its manifest and marketplace entry. A product rename changes this,
# plugins/agentguard-claude/.claude-plugin/plugin.json and .claude-plugin/marketplace.json.
PLUGIN_NAME = "agentguard"
SHIM_MODULE = "agentguard.adapters.claude_code.shim"
OWNERSHIP_HEADER = "X-AgentGuard"
MAX_SETTINGS_BYTES = 5_000_000


def claude_config_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Where Claude Code keeps user settings and plugins (honours ``CLAUDE_CONFIG_DIR``)."""
    env = os.environ if environ is None else environ
    raw = env.get("CLAUDE_CONFIG_DIR")
    return Path(raw).expanduser() if raw else Path.home() / ".claude"


def user_settings_path(environ: Mapping[str, str] | None = None) -> Path:
    return claude_config_dir(environ) / "settings.json"


def project_settings_paths(project: Path) -> list[tuple[str, Path]]:
    return [
        ("project", project / ".claude" / "settings.json"),
        ("local", project / ".claude" / "settings.local.json"),
    ]


def load_json(path: Path) -> Any:
    """Parsed JSON, or ``None`` when the file is missing, oversized or invalid."""
    try:
        if path.is_symlink() and not path.exists():
            return None
        if path.stat().st_size > MAX_SETTINGS_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


# -- ownership -----------------------------------------------------------------------------


def command_argv(hook: dict[str, Any]) -> list[str]:
    """Normalize current and legacy command-hook representations for ownership checks."""
    command = hook.get("command")
    if not isinstance(command, str) or not command:
        return []
    legacy_args = hook.get("args")
    if isinstance(legacy_args, list) and all(isinstance(arg, str) for arg in legacy_args):
        return [command, *legacy_args]
    try:
        return shlex.split(command)
    except ValueError:
        return []


def is_ours_hook(hook: Any) -> bool:
    """Identify one AgentGuard settings hook without matching a user's arbitrary text.

    HTTP hooks carry an explicit header marker. Command hooks are recognised by the shim
    module plus one of its two flags; older releases emitted ``command`` + ``args`` and
    that shape is still recognised, so reinstall/uninstall stays reversible after an
    upgrade. A user hook that merely mentions the word "agentguard" is not ours.
    """
    if not isinstance(hook, dict):
        return False
    headers = hook.get("headers")
    if isinstance(headers, dict) and headers.get(OWNERSHIP_HEADER) == "1":
        return True
    argv = command_argv(hook)
    return SHIM_MODULE in argv and ("--ensure-daemon" in argv or "--health" in argv)


def is_ours_group(group: Any) -> bool:
    """Whether a Claude hook group contains an AgentGuard-owned hook."""
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    return isinstance(hooks, list) and any(is_ours_hook(hook) for hook in hooks)


def hooks_installed(path: Path) -> bool:
    """Whether this settings file carries AgentGuard's settings-based hooks."""
    data = load_json(path)
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return False
    return any(
        is_ours_group(group)
        for groups in hooks.values()
        if isinstance(groups, list)
        for group in groups
    )


def legacy_hook_files(
    project: Path | None, environ: Mapping[str, str] | None = None
) -> list[tuple[str, Path]]:
    """``[(scope, path)]`` for each settings file Claude Code reads that has our hooks."""
    candidates = [("user", user_settings_path(environ))]
    if project is not None:
        candidates += project_settings_paths(project)
    return [(scope, path) for scope, path in candidates if hooks_installed(path)]


# -- the plugin ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PluginInstall:
    plugin_id: str
    scope: str
    project_path: str | None
    install_path: str | None
    version: str | None


def plugin_installs(environ: Mapping[str, str] | None = None) -> list[PluginInstall]:
    """Install records of AgentGuard's plugin, from ``installed_plugins.json``."""
    record = load_json(claude_config_dir(environ) / "plugins" / "installed_plugins.json")
    plugins = record.get("plugins") if isinstance(record, dict) else None
    if not isinstance(plugins, dict):
        return []
    found: list[PluginInstall] = []
    for plugin_id, entries in plugins.items():
        if not isinstance(plugin_id, str) or plugin_id.split("@", 1)[0] != PLUGIN_NAME:
            continue
        for entry in entries if isinstance(entries, list) else [entries]:
            if not isinstance(entry, dict):
                continue
            found.append(
                PluginInstall(
                    plugin_id=plugin_id,
                    scope=str(entry.get("scope") or "user"),
                    project_path=_str_or_none(entry.get("projectPath")),
                    install_path=_str_or_none(entry.get("installPath")),
                    version=_str_or_none(entry.get("version")),
                )
            )
    return found


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def plugin_enabled_setting(
    plugin_id: str, project: Path | None, environ: Mapping[str, str] | None = None
) -> bool | None:
    """The ``enabledPlugins`` value Claude Code would apply, or ``None`` if unset.

    Precedence, highest first: local, project, user — the order Claude Code documents.
    Managed settings and ``--settings`` are not visible from here.
    """
    sources = [path for _, path in reversed(project_settings_paths(project))] if project else []
    sources.append(user_settings_path(environ))
    for path in sources:
        data = load_json(path)
        enabled = data.get("enabledPlugins") if isinstance(data, dict) else None
        if isinstance(enabled, dict) and isinstance(enabled.get(plugin_id), bool):
            return enabled[plugin_id]
    return None


def active_plugin_installs(
    project: Path | None, environ: Mapping[str, str] | None = None
) -> list[PluginInstall]:
    """Plugin installs that apply to a session in ``project`` and are not disabled."""
    active = []
    for install in plugin_installs(environ):
        if install.scope in ("project", "local"):
            if project is None or not install.project_path:
                continue
            try:
                scoped = Path(install.project_path).resolve()
                here = project.resolve()
            except OSError:
                continue
            if here != scoped and scoped not in here.parents:
                continue
        if plugin_enabled_setting(install.plugin_id, project, environ) is False:
            continue
        active.append(install)
    return active
