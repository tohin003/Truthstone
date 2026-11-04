"""Wire constants shared by the daemon-side adapter and the command-hook processes.

Stdlib-only on purpose (it imports only ``truthstone.names``, itself stdlib-only):
``shim.py`` and ``plugin.py`` run as hook processes and must not pull in pydantic or
FastAPI (that would triple their start-up cost), while ``translate.py`` runs inside the
daemon. Anything both sides must agree on lives here, once.
"""

from __future__ import annotations

from typing import Any

from truthstone import names

HOOK_PATH = "/hook/claude-code"

# Per-session modes (R10). A command hook sees the session's own environment; the daemon
# does not. The hook therefore registers ``TRUTHSTONE_DISABLE`` / ``TRUTHSTONE_OBSERVE``
# for its session with this pseudo-event, which the adapter consumes and never forwards
# to the core.
SESSION_MODE_EVENT = "TruthstoneSessionMode"
SESSION_MODE_FIELD = "truthstone_session_mode"
SESSION_MODES = ("disabled", "observe", "guard")


def flag(environ: Any, name: str) -> bool:
    """A boolean switch, honouring the same setting under a former product name."""
    return names.env_flag(name, environ)


def session_mode_from_env(environ: Any) -> str:
    """The mode a developer asked for when they launched this session."""
    if names.env_flag("TRUTHSTONE_DISABLE", environ):
        return "disabled"
    if names.env_flag("TRUTHSTONE_OBSERVE", environ):
        return "observe"
    return "guard"


def session_mode_message(session_id: str, mode: str) -> dict[str, Any]:
    """The registration message a command hook sends for its session."""
    return {
        "hook_event_name": SESSION_MODE_EVENT,
        "session_id": session_id,
        SESSION_MODE_FIELD: mode,
    }
