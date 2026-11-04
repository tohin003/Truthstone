"""Which symlinks AgentGuard trusts on the way to its private files — one rule for every
entry point (R11).

``~/.agentguard`` holds the daemon's token and handshake, so every private path is checked
for symlinked components: a link someone else can swap would redirect credentials. Two
kinds of link are trusted anyway, because refusing them made AgentGuard refuse to run:

* **system links**, for any private path: macOS's ``/tmp`` and ``/var`` aliases (by exact
  target), and any root-owned link in a root-owned directory nobody else can write —
  Fedora Silverblue's ``/home -> var/home``, FreeBSD's ``/home -> usr/home``. Root can
  redirect anything anyway, so trusting root's own links costs nothing;
* **links on the way to the configured home**: one root or this user placed, in a
  directory nobody else can change (owner-only, or sticky like ``/tmp``) — a dotfiles
  manager's ``~/.agentguard -> ~/dotfiles/agentguard``. The home is resolved through
  them once, at the boundary, so everything downstream sees a path with no links at all.

Any other link leaves the home as it was configured, and the private-path checks refuse
it with their usual error; readers refuse to take a handshake from behind it.

``core/config.py`` (the daemon and the CLI), ``daemon/lifecycle.py`` (locks, markers and
logs), the Claude shim and the Codex hook all ask this module, so they cannot disagree
about where the home is. Stdlib only, and only ``os`` and ``stat`` (plus ``agentguard.names``,
itself stdlib-only): the Codex hook imports it on every tool call.
"""

from __future__ import annotations

import os
import stat

from agentguard import names

ENV_HOME = "AGENTGUARD_HOME"
DEFAULT_HOME = "~/.agentguard"

# The account that owns the operating system's own layout. A module constant so tests
# can stand in for root without being root.
ROOT_UID = 0
SYSTEM_ALIASES = {"/tmp": "/private/tmp", "/var": "/private/var"}


def trusted_system_link(path: str, mode: int | None = None) -> bool:
    """A link only the system could have placed — never a user's."""
    path = str(path)
    try:
        info = os.lstat(path)
        mode = info.st_mode if mode is None else mode
        target = SYSTEM_ALIASES.get(path)
        if target is not None:
            return info.st_uid == 0 and mode & 0o022 == 0 and os.path.realpath(path) == target
        if info.st_uid != ROOT_UID:
            return False
        parent = os.stat(os.path.dirname(path) or os.sep)
        return parent.st_uid == ROOT_UID and not parent.st_mode & 0o022
    except (OSError, ValueError):
        return False


def trusted_home_link(path: str) -> bool:
    """For the configured home only: a link that root or this user placed, where nobody
    else can swap it (an owner-only directory, or a sticky one such as /tmp)."""
    getuid = getattr(os, "getuid", None)
    if getuid is None:  # pragma: no cover - Windows: no POSIX ownership to reason about
        return False
    path = str(path)
    try:
        info = os.lstat(path)
        if trusted_system_link(path, info.st_mode):
            return True
        parent = os.stat(os.path.dirname(path) or os.sep)
    except (OSError, ValueError):
        return False
    owners = (ROOT_UID, getuid())
    if info.st_uid not in owners or parent.st_uid not in owners:
        return False
    return not parent.st_mode & 0o022 or bool(parent.st_mode & stat.S_ISVTX)


def _lexical(path: str) -> str:
    """``path`` spelled as ``pathlib`` would: no empty or ``.`` components, no trailing
    slash. ``..`` is kept — collapsing it is only correct where no link is involved."""
    rooted = path.startswith(os.sep)
    parts = [part for part in path.split(os.sep) if part not in ("", ".")]
    joined = os.sep.join(parts)
    return os.sep + joined if rooted else (joined or ".")


def resolve_home(home: str) -> tuple[str, bool]:
    """``(path, trusted)`` for a configured home.

    With no link on the way (macOS's /tmp and /var aliases aside), ``(home, True)``.
    When every link is trusted, the canonical path and ``True``. Otherwise ``home``
    unchanged and ``False``: the private-path checks will refuse it, and nothing should
    be read from behind it either. Never raises.
    """
    try:
        absolute = _lexical(home if os.path.isabs(home) else os.path.join(os.getcwd(), home))
        links: list[str] = []
        current = absolute
        while True:
            try:
                if stat.S_ISLNK(os.lstat(current).st_mode) and current not in SYSTEM_ALIASES:
                    links.append(current)
            except OSError:
                pass
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        if not links:
            return home, True
        if all(trusted_home_link(link) for link in links):
            return os.path.realpath(absolute), True
        return home, False
    except (OSError, ValueError):  # no working directory, a NUL in the variable, ...
        return home, False


def canonical_home(home: str) -> str:
    """The configured home through trusted links, else as configured."""
    return resolve_home(home)[0]


def configured_home(environ: dict[str, str] | None = None) -> str:
    """``AGENTGUARD_HOME`` (empty means unset) or ``~/.agentguard``, as configured.

    Former product names count, by `names.data_dir`'s rule: the same setting under a
    former name is the fallback, and a former name's directory is used while only that
    one exists.
    """
    explicit = names.env(ENV_HOME, environ)
    if explicit:
        return os.path.expanduser(explicit)
    return names.migrated(os.path.expanduser(DEFAULT_HOME))


def home(environ: dict[str, str] | None = None) -> str:
    """The home every entry point uses: configured, then resolved through trusted links."""
    return canonical_home(configured_home(environ))
