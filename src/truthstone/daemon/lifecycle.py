"""Small stdlib-only process/lifecycle primitives used by the daemon and shim.

The command-hook shim intentionally does not import the application's configuration or
FastAPI stack.  Keeping the lock implementation here lets the shim and the CLI use the
same inter-process startup claim without paying that import cost.
"""

from __future__ import annotations

import contextlib
import os
import stat
import time
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from truthstone.daemon import private_paths

try:  # POSIX (Linux/macOS/BSD), where Truthstone normally runs.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on Windows.
    fcntl = None  # type: ignore[assignment]

try:  # Windows fallback.
    import msvcrt
except ImportError:  # pragma: no cover - exercised only on POSIX.
    msvcrt = None  # type: ignore[assignment]


DEFAULT_LOCK_TIMEOUT_S = 10.0
POLL_S = 0.025
# daemon.log is the daemon's stdout and stderr. It is rotated past this size, both by the
# process that spawns a daemon and by the daemon itself (`daemon/logs.py`), keeping this
# many old files: at most about (DAEMON_LOG_BACKUPS + 1) * DAEMON_LOG_MAX_BYTES in all.
DAEMON_LOG_MAX_BYTES = 4 * 1024 * 1024
DAEMON_LOG_BACKUPS = 2


def _trusted_system_alias(path: Path, mode: int) -> bool:
    """A link only the system could have placed, never a user's — the same rule as
    ``core/config.py`` (``daemon/private_paths.py``). It used to accept macOS's /tmp and
    /var aliases only, so a lock under Silverblue's `/home -> var/home` was refused."""
    return private_paths.trusted_system_link(str(path), mode)


def _assert_no_symlink_components(path: Path) -> None:
    """Reject existing symlink ancestors before creating lifecycle files."""
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    current = candidate
    while True:
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise OSError(f"could not inspect private path component: {current}") from exc
        else:
            if stat.S_ISLNK(mode) and not _trusted_system_alias(current, mode):
                raise OSError(f"refusing to use symlinked private path component: {current}")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _open_lock_file(path: Path) -> BinaryIO:
    """Open a private lock file without following a symlink."""
    parent = path.parent
    # The shim runs without importing the full config module, so repeat the critical
    # private-directory checks here.  In particular, never let a user-controlled
    # TRUTHSTONE_HOME symlink redirect lifecycle files elsewhere.
    _assert_no_symlink_components(parent)
    if parent.is_symlink() and not _trusted_system_alias(parent, parent.lstat().st_mode):
        raise OSError("refusing to use a symlink as the lock directory")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_no_symlink_components(parent)
    try:
        parent_stat = os.lstat(parent)
    except OSError:
        raise
    trusted_alias = stat.S_ISLNK(parent_stat.st_mode) and _trusted_system_alias(
        parent, parent_stat.st_mode
    )
    if (stat.S_ISLNK(parent_stat.st_mode) and not trusted_alias) or (
        not stat.S_ISDIR(parent_stat.st_mode) and not trusted_alias
    ):
        raise OSError("lock parent is not a directory")
    if path.is_symlink():
        raise OSError("refusing to use a symlink as the lock file")
    with contextlib.suppress(OSError):
        os.chmod(path.parent, 0o700)
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("lock path is not a regular file")
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise
    # Existing installations may have created this before private-file permissions were
    # introduced.  A lock file contains no secret, but keeping it private avoids leaking
    # lifecycle metadata and makes the whole ~/.truthstone tree consistently owner-only.
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    else:  # pragma: no cover - legacy platforms without fchmod.
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    return os.fdopen(fd, "a+b", buffering=0)


def open_private_append(path: str | Path) -> BinaryIO:
    """Open a daemon log/marker file without following a symlink.

    These files are not credentials, but they contain local process and lifecycle
    metadata.  A normal ``open(..., 'ab')`` would use the caller's umask and commonly
    create them as ``0644``; keep them consistent with the rest of the private home.
    """
    target = Path(path)
    parent = target.parent
    _assert_no_symlink_components(parent)
    if parent.is_symlink() and not _trusted_system_alias(parent, parent.lstat().st_mode):
        raise OSError("refusing to use a symlink as the private-file directory")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_no_symlink_components(parent)
    if not parent.is_dir():
        raise OSError("private-file parent is not a directory")
    with contextlib.suppress(OSError):
        os.chmod(parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("private log path is not a regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        else:  # pragma: no cover - legacy platforms without fchmod.
            os.chmod(target, 0o600)
        return os.fdopen(fd, "ab", buffering=0)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise


def rotate_log(
    path: str | Path, max_bytes: int | None = None, backups: int | None = None
) -> bool:
    """Move an oversized log aside: ``log`` -> ``log.1`` -> ... -> ``log.<backups>``.

    Returns whether it rotated. Only a regular file at least ``max_bytes`` long is moved,
    and only by ``rename``, which never follows a symlink. The oldest backup is replaced,
    so the log and its backups together stay below ``(backups + 1) * max_bytes`` plus
    whatever is written after the last check. Never raises: a log that cannot be rotated
    is still a log.
    """
    limit = DAEMON_LOG_MAX_BYTES if max_bytes is None else max_bytes
    keep = DAEMON_LOG_BACKUPS if backups is None else max(1, backups)
    target = Path(path)
    try:
        info = os.lstat(target)
        if not stat.S_ISREG(info.st_mode) or info.st_size < limit:
            return False
        _assert_no_symlink_components(target.parent)
        for index in range(keep - 1, 0, -1):
            older = target.with_name(f"{target.name}.{index}")
            if os.path.lexists(older):
                os.replace(older, target.with_name(f"{target.name}.{index + 1}"))
        os.replace(target, target.with_name(f"{target.name}.1"))
        return True
    except OSError:
        return False


def create_private_marker(path: str | Path, content: str = "") -> bool:
    """Create a private marker exactly once; return ``False`` if it already exists."""
    target = Path(path)
    parent = target.parent
    _assert_no_symlink_components(parent)
    if parent.is_symlink() and not _trusted_system_alias(parent, parent.lstat().st_mode):
        raise OSError("refusing to use a symlink as the private-file directory")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_no_symlink_components(parent)
    if not parent.is_dir():
        raise OSError("private-file parent is not a directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        return False
    try:
        os.write(fd, content.encode())
        os.fsync(fd)
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        else:  # pragma: no cover - legacy platforms without fchmod.
            os.chmod(target, 0o600)
        return True
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)


def _try_acquire(handle: BinaryIO) -> bool:
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    if msvcrt is not None:  # pragma: no cover - Windows-only branch.
        # msvcrt.locking locks bytes from the current cursor.  Ensure a byte exists and
        # always lock the first one; the file itself is otherwise never read or written.
        try:
            handle.seek(0)
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except (OSError, ValueError):
            return False

    # A Python build with neither platform locking API is unusual.  Returning False is
    # safer than pretending an inter-process lock exists: callers fail open or report a
    # bounded startup error rather than launching duplicate daemons.
    return False


def _release(handle: BinaryIO) -> None:
    if fcntl is not None:
        with contextlib.suppress(OSError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    elif msvcrt is not None:  # pragma: no cover - Windows-only branch.
        with contextlib.suppress(OSError, ValueError):
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def interprocess_lock(
    path: str | Path, timeout: float | None = DEFAULT_LOCK_TIMEOUT_S
) -> Iterator[bool]:
    """Try to hold an advisory inter-process lock for a bounded period.

    The yielded boolean is ``False`` when the lock could not be acquired (including an
    unwritable home directory).  Callers must treat that exactly like any other daemon
    transport failure: never block the host agent indefinitely and never start a second
    owner speculatively.
    """
    handle: BinaryIO | None = None
    acquired = False
    try:
        try:
            handle = _open_lock_file(Path(path))
        except OSError:
            yield False
            return

        limit = None if timeout is None else max(0.0, float(timeout))
        deadline = None if limit is None else time.monotonic() + limit
        while True:
            if _try_acquire(handle):
                acquired = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(POLL_S)
        yield acquired
    finally:
        if handle is not None:
            if acquired:
                _release(handle)
            with contextlib.suppress(OSError, ValueError):
                handle.close()


def startup_lock_path(home: str | Path) -> Path:
    return Path(home) / "daemon.start.lock"


def handshake_lock_path(home: str | Path) -> Path:
    return Path(home) / "daemon.handshake.lock"
