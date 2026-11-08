"""One stockroom command at a time per inventory file.

While a command runs it holds ``<inventory>.lock``, a small file naming its process id and start
time, and it removes the file when it finishes, so two terminals cannot overwrite each other's
changes. A command that is killed (a power cut, ``kill -9``) cannot remove its lock.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


class LockedError(Exception):
    """Another stockroom process holds the inventory's lock."""


def lock_path(inventory: str | Path) -> Path:
    inventory = Path(inventory)
    return inventory.with_name(inventory.name + ".lock")


def acquire(inventory: str | Path) -> Path:
    """Take the inventory's lock and return its path; raise LockedError if it is held."""
    lock = lock_path(inventory)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        holder = lock.read_text(encoding="utf-8", errors="replace").strip() or "unknown process"
        raise LockedError(
            f"{inventory} is locked by another stockroom process ({holder}); "
            "if it is no longer running, see the README, 'After a crash'"
        ) from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"pid {os.getpid()}, since {datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}\n")
    return lock


def release(lock: Path) -> None:
    lock.unlink(missing_ok=True)
