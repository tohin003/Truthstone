"""Claude Code *plugin* entry points.

    hooks/hooks.json -> scripts/hook.sh <kind>
                     -> python -I -m truthstone.adapters.claude_code.plugin <command>

The plugin (``plugins/truthstone-claude``) is a thin launcher: it installs this package
into its data directory and hands every event to it, so Truthstone upgrades never require
editing plugin files. Per-tool events go to ``forward.py`` (one lean process per call);
the once-per-session and once-per-prompt work is here:

``session-start [--restart-daemon]``
    Decide whether the plugin must stand down because Truthstone's settings-based hooks
    already cover this session (see :func:`stand_down`), make sure the daemon runs,
    forward the SessionStart event, and say — once, as a ``systemMessage`` — when this
    session is not guarded.
``prompt``
    Revive a dead daemon or warn once; report daemon states that guard nothing; forward
    UserPromptSubmit.
``status``
    A human-readable runtime report, for ``/truthstone:doctor``.
``on`` / ``off`` / ``restart-daemon``
    Switch guarding and restart the daemon so the switch takes effect.

Stdlib-only (it imports the shim and the settings scanner, both stdlib-only): this runs
once per prompt and must not pay for pydantic.

Invariants, as everywhere in the adapter: never grant permissions; fail open (every path
exits 0, and every problem degrades to "no decision"); never fail *silently* — a session
that is not guarded is told so once, at the moment it starts or the moment it breaks.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

from truthstone.adapters.claude_code import forward, protocol, settings_scan, shim

PROMPT_TIMEOUT_S = 8.0
SESSION_START_TIMEOUT_S = 15.0

UNGUARDED = (
    "Truthstone could not start its local service, so this session is UNGUARDED. "
    "Run /truthstone:doctor to see why. Your work continues either way."
)


# -- where things are ----------------------------------------------------------------------


def plugin_data() -> Path | None:
    raw = os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(raw) if raw else None


def project_dir(payload: dict) -> Path | None:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
    return Path(raw) if isinstance(raw, str) and raw else None


# -- standing down beside settings-based hooks ---------------------------------------------


def standdown_markers(data: Path, project: Path | None) -> dict[str, Path]:
    marks = data / "standdown"
    out = {"user": marks / "user"}
    if project is not None:
        out["project"] = marks / forward.project_key(str(project))
    return out


def stand_down(payload: dict) -> list[tuple[str, Path]]:
    """Find settings-based Truthstone hooks for this session and record the result.

    With both installs active, every event would be handled twice. The plugin is the one
    that can step aside — settings hooks cannot see it — so wherever settings hooks are
    present it writes a marker that ``forward.py`` checks on every event, and says why.
    The markers are recomputed at every session start, so removing the old hooks is
    picked up by the next session.
    """
    data = plugin_data()
    if data is None:
        return []
    project = project_dir(payload)
    found = settings_scan.legacy_hook_files(project)
    scopes = {scope for scope, _ in found}
    markers = standdown_markers(data, project)
    wanted = {"user": "user" in scopes, "project": bool(scopes & {"project", "local"})}
    for name, path in markers.items():
        try:
            if wanted.get(name):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps([str(p) for _, p in found]) + "\n", encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
        except OSError:
            continue
    return found


def standdown_message(found: list[tuple[str, Path]]) -> str:
    fixes = []
    for scope, path in found:
        if scope == "user":
            fixes.append(f"`truthstone uninstall claude --global` (removes them from {path})")
        elif scope == "local":
            fixes.append(f"`truthstone uninstall claude --project` in this project ({path})")
        else:
            fixes.append(f"remove Truthstone's hooks from {path}")
    return (
        "Truthstone plugin is standing by: Truthstone's settings-based hooks are also "
        "installed, and they keep guarding this session. To switch to the plugin, run "
        + "; ".join(fixes)
        + "."
    )


# -- hook commands -------------------------------------------------------------------------


def _with_notices(out: dict, notices: list[str]) -> dict:
    if notices:
        out = dict(out)
        out["systemMessage"] = "\n".join(notices)
    return out


def session_start(payload: dict, restart: bool = False) -> dict:
    session_id = str(payload.get("session_id") or "")
    mode = protocol.session_mode_from_env(os.environ)
    if mode == "disabled":
        return {}

    found = stand_down(payload)
    if found:
        return {"systemMessage": standdown_message(found)}

    if restart:
        restart_daemon()
    hs = shim.ensure_daemon()
    body = shim.health_body(hs)
    if body is None:
        # The prompt hook would say the same; mark it so the developer hears it once.
        shim.notify_once(session_id)
        return {"systemMessage": UNGUARDED}

    if mode == "observe":
        shim.register_session_mode(hs, session_id, mode)
    notices = shim.pending_notices(body, session_id, mode)
    return _with_notices(shim.post(hs, payload, SESSION_START_TIMEOUT_S), notices)


def prompt(payload: dict) -> dict:
    if forward.standing_down():
        return {}
    session_id = str(payload.get("session_id") or "")
    mode = protocol.session_mode_from_env(os.environ)
    if mode == "disabled":
        return {}

    hs = shim.ensure_daemon()
    body = shim.health_body(hs)
    if body is None:
        return {"systemMessage": UNGUARDED} if shim.notify_once(session_id) else {}

    if mode == "observe":
        shim.register_session_mode(hs, session_id, mode)
    notices = shim.pending_notices(body, session_id, mode)
    return _with_notices(shim.post(hs, payload, PROMPT_TIMEOUT_S), notices)


# -- controls ------------------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    """Run this runtime's own CLI. ``-P``: the caller's cwd is the user's repository."""
    return subprocess.run(
        [sys.executable, "-P", "-m", "truthstone.cli.main", *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )


def restart_daemon() -> bool:
    if shim.health_body(shim._handshake()) is not None:
        _cli("daemon", "stop")
    return shim.health_body(shim.ensure_daemon()) is not None


def switch(enabled: bool) -> int:
    result = _cli("on" if enabled else "off")
    if result.returncode != 0:
        sys.stdout.write(result.stdout + result.stderr)
        return 0
    running = restart_daemon()
    state = "ON — guarding" if enabled else "OFF — hooks stay installed and decide nothing"
    sys.stdout.write(f"Truthstone is {state}.\n")
    sys.stdout.write(
        "This applies to every Claude Code session on this machine.\n"
        if running
        else "The daemon is not running; the setting applies when it next starts.\n"
    )
    return 0


def status() -> int:
    data = plugin_data()
    write = sys.stdout.write
    write("Truthstone plugin\n")
    write(f"  runtime      {sys.executable}\n")
    with contextlib.suppress(Exception):
        from truthstone import __version__

        write(f"  version      {__version__}\n")
    if data is not None:
        write(f"  data         {data}\n")
        ready = data / "runtime.ready"
        with contextlib.suppress(OSError):
            lines = ready.read_text(encoding="utf-8").splitlines()
            if len(lines) >= 3:
                write(f"  source       {lines[2]}\n")

    hs = shim._handshake()
    body = shim.health_body(hs)
    if body is None:
        write("  daemon       not running (it starts with the next session or prompt)\n")
    else:
        flags = [
            label
            for label, on in (
                ("switched off", body.get("enabled") is False),
                ("observe-only", body.get("observing") is True),
            )
            if on
        ]
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        write(f"  daemon       pid {body.get('pid')} on {hs.get('host')}:{hs.get('port')}{suffix}\n")

    project = Path.cwd()
    found = settings_scan.legacy_hook_files(project)
    if found:
        write("  this project the plugin is STANDING BY: settings-based hooks are installed in\n")
        for _, path in found:
            write(f"               {path}\n")
    else:
        write("  this project guarded by the plugin\n")
    return 0


# -- entry ---------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""
    try:
        if command in ("session-start", "prompt"):
            payload = shim.read_payload()
            if payload is None:
                return 0
            if command == "session-start":
                out = session_start(payload, restart="--restart-daemon" in args)
            else:
                out = prompt(payload)
            if out:
                sys.stdout.write(json.dumps(out))
            return 0
        if command == "status":
            return status()
        if command in ("on", "off"):
            return switch(command == "on")
        if command == "restart-daemon":
            ok = restart_daemon()
            sys.stdout.write("daemon restarted\n" if ok else "daemon did not come back; see doctor\n")
            return 0
    except Exception:  # noqa: BLE001 - fail open: a broken entry point must not block the agent
        return 0
    sys.stderr.write(f"usage: python -m {__spec__.name if __spec__ else 'plugin'} <command>\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
