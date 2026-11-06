"""The native forwarder's build: ``forward_native.c``, compiled once per version into the lean dir.

Codex runs every hook as a new process, and after the model's thinking pause the machine is
cold: starting Python then costs 35-40 ms (``python -I -S``), a small C program a few. So at
SessionStart the runtime also compiles ``forward_native.c``, a C port of ``forward.py`` (which
stays the specification), into ``$PLUGIN_DATA/lean/forward-native``. The plugin launcher
prefers it for the events that only forward, then the Python forwarder, then the runtime.

The compile never holds SessionStart up. :func:`start` only checks a stamp and, when the binary
is missing or stale, removes it (so the Python forwarder answers meanwhile) and spawns the
builder, detached: this file, run as ``python -I -S native.py <lean dir>``. The builder compiles
with ``cc -O2`` to a temporary name, checks that the result runs, renames it into place, and
then writes the stamp (the source's hash, the flags and the platform), so it compiles once per
version. One build at a time (a lock file). No compiler, or any failure, leaves no binary and
says nothing: the launcher keeps to the Python forwarder.

Only into a real directory of this user's, made 0700 (never through a symlink), and only with a
``cc`` from an absolute ``PATH`` directory, in a clean environment: no include paths or flags
from elsewhere, and never anything from the repository the hook runs in.

Stdlib only and nothing from the package: the builder runs isolated (``-I -S``).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import subprocess
import sys
import time

SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forward_native.c")
BINARY = "forward-native"
STAMP = BINARY + ".stamp"
LOCK = BINARY + ".lock"
CFLAGS = ("-O2",)
COMPILE_TIMEOUT_S = 60.0
LOCK_STALE_S = 300.0  # a lock older than this is a dead builder's
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def stamp(source: bytes) -> str:
    """What a binary was built from: the source, the flags and the platform."""
    uname = os.uname()
    digest = hashlib.sha256(source)
    digest.update("\0".join(("", *CFLAGS, uname.sysname, uname.machine)).encode())
    return digest.hexdigest()


def private_dir(path: str) -> bool:
    """Whether ``path`` is a real directory (not a symlink) of this user's; made 0700."""
    getuid = getattr(os, "getuid", None)
    try:
        info = os.lstat(path)
        if getuid is None or not stat.S_ISDIR(info.st_mode) or info.st_uid != getuid():
            return False
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.chmod(path, 0o700)
    except OSError:
        return False
    return True


def current(lean: str, want: str) -> bool:
    """Whether ``lean`` holds a binary stamped ``want``: a regular executable file of ours."""
    try:
        info = os.lstat(os.path.join(lean, BINARY))
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or not info.st_mode & stat.S_IXUSR:
            return False
        fd = os.open(os.path.join(lean, STAMP), os.O_RDONLY | _NOFOLLOW)
        try:
            return os.read(fd, 256).decode("ascii", "replace").strip() == want
        finally:
            os.close(fd)
    except OSError:
        return False


def start(lean: str, python: str | None = None) -> subprocess.Popen | None:
    """At SessionStart: nothing when the binary is current. Otherwise remove the stale one and
    start the detached build, and return it (tests wait for it; the hook does not). Never
    raises, never waits."""
    lean = os.path.abspath(lean)
    lock = os.path.join(lean, LOCK)
    try:
        if not private_dir(lean):
            return None
        with open(SOURCE, "rb") as fh:
            want = stamp(fh.read())
        if current(lean, want) or not _take(lock):
            return None
    except OSError:
        return None
    try:
        if current(lean, want):  # a build finished while we looked
            _remove(lock)
            return None
        for name in (BINARY, STAMP):  # stale: the Python forwarder answers until the new one lands
            _remove(os.path.join(lean, name))
        return subprocess.Popen(
            [python or sys.executable, "-I", "-S", os.path.abspath(__file__), lean],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=lean,
            close_fds=True,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001 - no native forwarder is never a failure
        _remove(lock)
        return None


def compiler() -> str | None:
    """``cc`` from the absolute directories on PATH (a relative one would be the repository's).
    On macOS, /usr/bin/cc only stands in for the developer tools, and without them it offers to
    install them, in a dialog; it is used only when xcode-select names an installed toolchain."""
    import shutil

    path = _absolute_path()
    cc = shutil.which("cc", path=path) if path else None
    if cc is None:
        return None
    if sys.platform == "darwin" and os.path.realpath(cc).startswith("/usr/bin/"):
        try:
            probe = subprocess.run(
                ["/usr/bin/xcode-select", "-p"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                env=compiler_env(),
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        developer = probe.stdout.decode("utf-8", "replace").strip()
        if probe.returncode != 0 or not developer or not os.path.isdir(developer):
            return None
    return cc


def compiler_env() -> dict[str, str]:
    """The compiler's environment: an absolute PATH, and what finds the toolchain and a
    temporary directory. Nothing that adds include paths or flags (CPATH, CFLAGS, ...)."""
    env = {"PATH": _absolute_path(), "LC_ALL": "C"}
    for key in ("HOME", "TMPDIR", "DEVELOPER_DIR", "SDKROOT"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def build(lean: str) -> bool:
    """The detached builder: compile to a temporary name, check that it runs, rename it into
    place, then stamp it. The stamp names the very bytes compiled, whatever happens to the
    package meanwhile. Releases the build lock however it ends."""
    temporary = os.path.join(lean, f".{BINARY}.{os.getpid()}")
    copy, stamped = temporary + ".c", temporary + ".stamp"
    try:
        if not private_dir(lean):
            return False
        cc = compiler()
        if cc is None:
            return False
        with open(SOURCE, "rb") as fh:
            source = fh.read()
        for path in (copy, temporary, stamped):  # a dead builder's, under a reused PID
            _remove(path)
        _write_new(copy, source)
        compiled = subprocess.run(
            [cc, *CFLAGS, "-o", temporary, copy],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=compiler_env(),
            cwd=lean,
            timeout=COMPILE_TIMEOUT_S,
        )
        if compiled.returncode != 0 or not stat.S_ISREG(os.lstat(temporary).st_mode):
            return False
        os.chmod(temporary, 0o700)
        # It must run here and fail open: no input, nothing printed, exit 0.
        smoke = subprocess.run(
            [temporary], stdin=subprocess.DEVNULL, capture_output=True, env={}, cwd=lean, timeout=10
        )
        if smoke.returncode != 0 or smoke.stdout:
            return False
        os.replace(temporary, os.path.join(lean, BINARY))
        _write_new(stamped, (stamp(source) + "\n").encode())
        os.replace(stamped, os.path.join(lean, STAMP))
        return True
    except Exception:  # noqa: BLE001 - any failure means no native forwarder, silently
        return False
    finally:
        for path in (copy, temporary, stamped, os.path.join(lean, LOCK)):
            _remove(path)


def _absolute_path() -> str:
    return os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep) if os.path.isabs(d))


def _take(lock: str) -> bool:
    """One build at a time: the lock is a file only one process can create."""
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
        except FileExistsError:
            try:
                if time.time() - os.lstat(lock).st_mtime < LOCK_STALE_S:
                    return False
                os.unlink(lock)
            except OSError:
                return False
            continue
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    return False


def _write_new(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
    finally:
        os.close(fd)


def _remove(path: str) -> None:
    with contextlib.suppress(OSError):
        if os.path.isdir(path) and not os.path.islink(path):
            os.rmdir(path)  # only what a broken compiler could leave: an empty directory
        else:
            os.unlink(path)


def main(argv: list[str]) -> int:
    """``python -I -S native.py <lean dir>``: the detached build. Always exits 0."""
    if len(argv) == 1 and os.path.isabs(argv[0]):
        build(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
