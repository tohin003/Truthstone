"""Local state a command rewrote (v0.2): ignored files, older than the task, changed before "done".

The failure class
-----------------
To check a fix, an agent runs the project's real job in the working tree. The run does what it
does in production: it rotates a log, rewrites a local database, writes an export. Those files
are ignored (``.gitignore``): ``git status`` does not show them, the repository index never sees
them, and git cannot restore them. The task's own tests stay green, because they do not read the
local state the run replaced. The agent reports the fix verified, and the developer's local
history is gone.

What is checked
---------------
At the task's start (the prompt), the ignored files that already exist are recorded: path, size,
mtime and SHA-256, small files only, a bounded count (``snapshot``). At a Stop that claims done,
a recorded file whose content changed and that still exists is reported when

* no edit tool wrote it. An edit is the agent's visible choice; a command's side effect is not.
* neither the request nor the final message names it: its path, its file name with extension,
  or its own folder's path. "Fix the data in db/local.sqlite" asked for that change.

Deleted and new ignored files are listed as context and never reported on their own: clearing
ignored output is an ordinary request. Where an original went (a rotated log) is found by its
digest among the ignored files there now.

Not the class (day 3, the control audit): a file a command only appended to (its old bytes are
still its first bytes: a log the app or the tests write to lost nothing); a file named as a cache
(``rates-cache.json``); documentation build output (``docs/_build``, ``site/``) and the build
output a ``tsconfig.json`` declares (``outDir``, ``declarationDir``); and a generated file whose
first lines say not to edit it (setuptools-scm's version file, codegen output). Running the
tests, the docs build or the CLI rewrites those as a matter of course.

Silence
-------
No git, a git that does not answer in time, more ignored files or bytes than the caps, an
unreadable file, any exception: no snapshot, or no finding. A task rebuilt after a daemon restart
has no snapshot: the store keeps no per-file state (like the parse and file baselines), so the
check stays silent there. Dependency, cache and build folders (``IndexSettings.exclude_dirs``
and the like) and files a test run rewrites by itself (``.coverage``, ...) are never recorded.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import stat
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from truthstone.core.enums import FailureMode, ReasonCategory, Severity
from truthstone.core.models import EvidenceRef

if TYPE_CHECKING:
    from truthstone.core.taskstate import TaskState
    from truthstone.repo.index import RepoIndex

log = logging.getLogger(__name__)

__all__ = [
    "IgnoredFile",
    "IgnoredSnapshot",
    "concerns",
    "declared_outputs",
    "ignored_files",
    "named",
    "remember",
    "snapshot",
]

MAX_FILES = 2_000  # ignored files recorded at most; with more, nothing is recorded
MAX_FILE_BYTES = 1_000_000  # larger files are not recorded
MAX_TOTAL_BYTES = 16_000_000  # bytes hashed per snapshot at most; past it, nothing is recorded
MAX_WALK_ENTRIES = 20_000  # entries visited inside ignored folders before giving up
GIT_TIMEOUT_S = 2.0  # each git call; a slower git means no snapshot
DEADLINE_S = 1.0  # the whole snapshot; a slower one is dropped
MAX_LISTED = 6  # files named in the message, per kind

# Folders that hold dependencies, caches or build output: their churn is never the task's
# question. ``IndexSettings.exclude_dirs`` comes on top of these.
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".tox",
        ".nox",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hypothesis",
        ".pytype",
        ".pyre",
        ".cache",
        "dist",
        "build",
        "target",
        "out",
        "coverage",
        "htmlcov",
        ".eggs",
        "site-packages",
        "__pypackages__",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".angular",
        ".turbo",
        ".parcel-cache",
        ".nyc_output",
        ".sass-cache",
        ".gradle",
        ".terraform",
        ".serverless",
        ".expo",
        ".dart_tool",
        ".yarn",
        ".pnpm-store",
        ".npm",
        "bower_components",
        "vendor",
        ".idea",
        ".vscode",
        # documentation builds: sphinx, mkdocs, jekyll, docusaurus, storybook (day 3)
        "_build",
        "site",
        "_site",
        ".docusaurus",
        "storybook-static",
    }
)
_SKIP_DIR_SUFFIXES = (".egg-info", ".dist-info")
# A file named as a cache (`rates-cache.json`, `http_cache.sqlite`), like the cache folders above.
_CACHE_NAME = re.compile(r"(?:^|[._-])cache(?:[._-]|$)", re.IGNORECASE)
# A generated file says not to edit it in its first lines: setuptools-scm ("don't change, don't
# track in version control"), codegen ("DO NOT EDIT", "@generated").
_GENERATED = re.compile(
    rb"\bdo\s+not\s+(?:edit|modify|change|make\s+(?:direct\s+)?changes)\b|\bdon'?t\s+(?:edit|modify|change)\b"
    rb"|@generated\b",
    re.IGNORECASE,
)
_GENERATED_HEAD = 400  # bytes read for the banner
# A tsconfig's declared build output: the first folder of `outDir` / `declarationDir`.
_TS_OUTPUT = re.compile(r'"(?:outDir|declarationDir)"\s*:\s*"(?:\./)?([^"/]+)')
# Files a test or a tool run rewrites as a matter of course.
_SKIP_NAMES = frozenset(
    {
        ".coverage",
        "coverage.xml",
        "coverage.json",
        "lcov.info",
        ".DS_Store",
        "Thumbs.db",
        ".eslintcache",
        ".stylelintcache",
    }
)
_SKIP_SUFFIXES = (".pyc", ".pyo", ".tsbuildinfo", ".swp", ".swo")


@dataclass(frozen=True, slots=True)
class IgnoredFile:
    """One ignored, untracked file as the task found it."""

    size: int
    mtime_ns: int
    digest: str  # SHA-256 of the bytes


@dataclass(slots=True)
class IgnoredSnapshot:
    """The ignored files that existed when the task began (``snapshot``)."""

    files: dict[str, IgnoredFile] = field(default_factory=dict)
    taken_at: float = 0.0
    elapsed_ms: float = 0.0


# -- which files ------------------------------------------------------------------------------------


def _skipped(path: str, exclude: frozenset[str]) -> bool:
    parts = PurePosixPath(path).parts
    if any(part in _SKIP_DIRS or part in exclude or part.endswith(_SKIP_DIR_SUFFIXES) for part in parts[:-1]):
        return True
    name = parts[-1] if parts else ""
    return (
        name in _SKIP_NAMES
        or name.startswith(".coverage.")
        or name.endswith(_SKIP_SUFFIXES)
        or _CACHE_NAME.search(name) is not None
    )


def declared_outputs(root: Path) -> tuple[str, ...]:
    """The build output folders the project's ``tsconfig.json`` declares (``outDir``,
    ``declarationDir``): ``lib/`` as surely as ``dist/``. Never raises; () when there is none."""
    try:
        full = Path(root) / "tsconfig.json"
        if not full.is_file() or full.stat().st_size > MAX_FILE_BYTES:
            return ()
        text = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    return tuple(dict.fromkeys(m for m in _TS_OUTPUT.findall(text) if m not in (".", "..")))


def _git_paths(root: Path, args: Iterable[str], deadline: float) -> list[str] | None:
    """``git ls-files`` output as paths, or None: no git, not a repository, or too slow."""
    timeout = min(GIT_TIMEOUT_S, deadline - time.monotonic())
    if timeout <= 0:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def ignored_files(root: Path, exclude: Iterable[str] = (), deadline: float | None = None) -> set[str] | None:
    """Every ignored, untracked regular file under ``root`` outside the skipped folders. None when
    it cannot tell, or when there are more than ``MAX_FILES``. A file git tracks is never one:
    git can restore it."""
    deadline = time.monotonic() + DEADLINE_S if deadline is None else deadline
    skip = frozenset(exclude)
    untracked = _git_paths(root, ("--others", "--ignored", "--exclude-standard", "--directory"), deadline)
    if untracked is None:
        return None
    out: set[str] = set()
    visited = 0
    for entry in untracked:
        if entry.endswith("/"):
            folder = entry.rstrip("/")
            if _skipped(folder + "/x", skip):
                continue
            for dirpath, dirnames, filenames in os.walk(root / folder):
                rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
                dirnames[:] = [d for d in dirnames if not _skipped(f"{rel}/{d}/x", skip)]
                visited += len(dirnames) + len(filenames)
                if visited > MAX_WALK_ENTRIES or time.monotonic() > deadline:
                    return None
                for name in filenames:
                    path = f"{rel}/{name}"
                    if not _skipped(path, skip):
                        out.add(path)
                if len(out) > MAX_FILES:
                    return None
        elif not _skipped(entry, skip):
            out.add(entry)
    return out if len(out) <= MAX_FILES else None


def _digest(full: Path, skip_generated: bool = False) -> tuple[int, int, str] | None:
    """(size, mtime_ns, sha256) of a small regular file, or None. With ``skip_generated``, None
    for a generated file too (a do-not-edit banner in its first lines)."""
    try:
        st = full.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_BYTES:
            return None
        with open(full, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if len(data) > MAX_FILE_BYTES:
        return None
    if skip_generated and _GENERATED.search(data[:_GENERATED_HEAD]):
        return None
    return st.st_size, st.st_mtime_ns, hashlib.sha256(data).hexdigest()


def snapshot(root: Path, exclude: Iterable[str] = ()) -> IgnoredSnapshot | None:
    """The ignored files that exist now (see the module docstring). Never raises; None when
    it cannot be taken within its bounds."""
    started = time.monotonic()
    deadline = started + DEADLINE_S
    try:
        listed = ignored_files(root, (*exclude, *declared_outputs(root)), deadline)
        if listed is None:
            return None
        files: dict[str, IgnoredFile] = {}
        hashed = 0
        for path in sorted(listed):
            got = _digest(root / path, skip_generated=True)
            if got is None:
                continue
            size, mtime_ns, digest = got
            hashed += size
            if hashed > MAX_TOTAL_BYTES or time.monotonic() > deadline:
                return None
            files[path] = IgnoredFile(size, mtime_ns, digest)
        return IgnoredSnapshot(files, time.time(), round((time.monotonic() - started) * 1000, 2))
    except Exception:
        log.debug("truthstone: could not record the ignored files", exc_info=True)
        return None


def remember(state: TaskState, root: Path, exclude: Iterable[str] = ()) -> None:
    """Take ``state``'s snapshot (the engine queues this at the task's prompt). Never raises."""
    state.ignored_snapshot = snapshot(root, exclude)


# -- naming ------------------------------------------------------------------------------------------


def _glued(char: str) -> bool:
    return bool(char) and (char.isalnum() or char in "_-")


def _occurs(text: str, needle: str, open_end: bool = False) -> bool:
    """Whether ``needle`` occurs in ``text`` as a whole path: not the tail of a longer word or
    path (``./`` may lead it), and, unless ``open_end``, not continued by one either."""
    start = 0
    while (at := text.find(needle, start)) >= 0:
        start = at + 1
        before = text[at - 1] if at else ""
        if (_glued(before) or before in "./") and text[max(0, at - 2) : at] != "./":
            continue
        if open_end:
            return True
        end = at + len(needle)
        after, then = text[end : end + 1], text[end + 1 : end + 2]
        if _glued(after) or after == "/" or (after == "." and _glued(then)):
            continue
        return True
    return False


def named(text: str, path: str) -> bool:
    """Whether ``text`` names ``path``: the path itself; its file name, when that has an
    extension (``worker.log``); or its own folder's path, written with its slash when it is one
    segment (``logs/``; ``var/data`` either way)."""
    if not text or not path:
        return False
    if _occurs(text, path):
        return True
    folder, _, name = path.rpartition("/")
    if "." in name and _occurs(text, name):
        return True
    if folder and _occurs(text, folder + "/", open_end=True):
        return True
    return "/" in folder and _occurs(text, folder)


# -- at Stop -----------------------------------------------------------------------------------------


def _changed(root: Path, path: str, before: IgnoredFile) -> bool | None:
    """True: content changed, the file is still there. False: unchanged, or only appended to (its
    old bytes are still its first bytes: nothing it held is gone). None: gone or unreadable."""
    full = root / path
    try:
        st = full.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return False
    if not stat.S_ISREG(st.st_mode):
        return False
    if st.st_size == before.size and st.st_mtime_ns == before.mtime_ns:
        return False
    if st.st_size > before.size:
        return not _appended(full, before)
    if st.st_size != before.size:
        return True
    now = _digest(full)
    return now is not None and now[2] != before.digest


def _appended(full: Path, before: IgnoredFile) -> bool:
    """Whether ``full`` starts with exactly the bytes ``before`` recorded (a log that grew)."""
    try:
        with open(full, "rb") as handle:
            head = handle.read(before.size)
    except OSError:
        return False
    return len(head) == before.size and hashlib.sha256(head).hexdigest() == before.digest


def _moved_to(root: Path, before: IgnoredFile, current: set[str], exclude: set[str]) -> str:
    """The ignored file that now holds ``before``'s exact content, if any (a rotated log)."""
    for path in sorted(current):
        if path in exclude:
            continue
        try:
            if (root / path).lstat().st_size != before.size:
                continue
        except OSError:
            continue
        got = _digest(root / path)
        if got is not None and got[2] == before.digest:
            return path
    return ""


def _listing(paths: list[str]) -> str:
    shown = ", ".join(f"`{p}`" for p in paths[:MAX_LISTED])
    return shown + (f" and {len(paths) - MAX_LISTED} more" if len(paths) > MAX_LISTED else "")


def concerns(state: TaskState, index: RepoIndex) -> list:
    """The untracked-state concern of this task, if any (``verify/arbiter.py`` IntegrityCheck)."""
    from truthstone.verify import arbiter

    snap = getattr(state, "ignored_snapshot", None)
    if not isinstance(snap, IgnoredSnapshot) or not snap.files:
        return []
    root = Path(index.root)
    edited = set(state.file_baselines)  # an edit tool was about to write these
    changed, gone = [], []
    for path in sorted(snap.files):
        if path in edited:
            continue
        verdict = _changed(root, path, snap.files[path])
        if verdict is None:
            gone.append(path)
        elif verdict:
            changed.append(path)
    if not changed:
        return []
    request, message = state.spec.prompt or "", arbiter.final_message()
    unnamed = [p for p in changed if not named(request, p) and not named(message, p)]
    if not unnamed:
        return []

    settings = getattr(index, "settings", None)
    current = ignored_files(root, (*getattr(settings, "exclude_dirs", ()), *declared_outputs(root))) or set()
    new = sorted(p for p in current if p not in snap.files and p not in edited)
    lines = []
    for path in unnamed[:MAX_LISTED]:
        went = _moved_to(root, snap.files[path], current, {path})
        where = f"; its original content is now `{went}`" if went else ""
        lines.append(f"  - `{path}` (modified{where})")
    if len(unnamed) > MAX_LISTED:
        lines.append(f"  - and {len(unnamed) - MAX_LISTED} more")
    what = "a local file" if len(unnamed) == 1 else f"{len(unnamed)} local files"
    text = f"Your commands changed {what} that the repository ignores and that existed before this task:\n"
    text += "\n".join(lines)
    left = []
    if new:
        left.append(f"left {_listing(new)}")
    if gone:
        left.append(f"removed {_listing(gone)}")
    if left:
        text += f"\nThey also {' and '.join(left)}."
    text += " Git cannot restore them. If a verification run did this, put the original files back and remove"
    text += " what the run created."
    finding = arbiter.finding(
        ReasonCategory.UNTRACKED_STATE,
        Severity.MEDIUM,
        summary=f"{len(unnamed)} ignored local file(s) changed by a command and not named",
        detail="; ".join(unnamed[:8]),
        evidence=[EvidenceRef(source="filesystem", path=p) for p in unnamed[:5]],
        mode=FailureMode.DESTRUCTIVE_ACTION,
    )
    return [arbiter.Concern(ReasonCategory.UNTRACKED_STATE, text, finding)]
