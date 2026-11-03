"""Wire constants shared by the daemon-side adapter and the command-hook processes.

Stdlib-only and import-free on purpose: ``shim.py`` and ``plugin.py`` run as hook
processes and must not pull in pydantic or FastAPI (that would triple their start-up
cost), while ``translate.py`` runs inside the daemon. Anything both sides must agree on
lives here, once.
"""

from __future__ import annotations

from typing import Any

HOOK_PATH = "/hook/claude-code"

# Per-session modes (R10). A command hook sees the session's own environment; the daemon
# does not. The hook therefore registers ``AGENTGUARD_DISABLE`` / ``AGENTGUARD_OBSERVE``
# for its session with this pseudo-event, which the adapter consumes and never forwards
# to the core.
SESSION_MODE_EVENT = "AgentGuardSessionMode"
SESSION_MODE_FIELD = "agentguard_session_mode"
SESSION_MODES = ("disabled", "observe", "guard")

_TRUE = {"1", "true", "yes", "on"}


def flag(environ: Any, name: str) -> bool:
    return str(environ.get(name, "")).strip().lower() in _TRUE


def session_mode_from_env(environ: Any) -> str:
    """The mode a developer asked for when they launched this session."""
    if flag(environ, "AGENTGUARD_DISABLE"):
        return "disabled"
    if flag(environ, "AGENTGUARD_OBSERVE"):
        return "observe"
    return "guard"


def session_mode_message(session_id: str, mode: str) -> dict[str, Any]:
    """The registration message a command hook sends for its session."""
    return {
        "hook_event_name": SESSION_MODE_EVENT,
        "session_id": session_id,
        SESSION_MODE_FIELD: mode,
    }
