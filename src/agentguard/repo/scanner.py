"""File discovery (SPEC §32, first stage of the evidence base).

Uses `git ls-files` where available: it is one subprocess call, it already honours
.gitignore and nested ignore files, and it is dramatically faster than walking a tree
that contains node_modules. Falls back to a filtered walk outside git repositories.

The scan runs on the hot path (every post-Bash sweep and every Stop), so it costs one
`lstat` per listed file plus one per distinct directory. The full canonical containment
check (`relative_path` plus `resolve`, about 20 syscalls) runs only for paths that
involve a symlink, which are the only paths it can reject: neither `git ls-files` nor a
non-following `os.walk` produces `..` or absolute paths, and anything that looks like
one is rejected lexically before the filesystem is touched (R5).
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from agentguard.core.config import IndexSettings
from agentguard.repo.models import (
    CONFIG_DIRS,
    CONFIG_FILENAMES,
    CONFIG_SUFFIXES,
    LANGUAGE_BY_EXT,
    FileRecord,
)
from agentguard.repo.paths import relative_path

# Path components that never appear in `git ls-files` or `os.walk` output. A listed path
# containing one is malformed or hostile, and is rejected without touching the disk.
_UNSAFE_PARTS: frozenset[str] = frozenset({"", ".", ".."})

TEST_DIR_NAMES: frozenset[str] = frozenset({"test", "tests", "__tests__", "spec", "specs", "e2e"})
TEST_FILE_PREFIXES: tuple[str, ...] = ("test_",)
TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test.py", "_test.go", ".test.js", ".test.ts", ".test.tsx", ".test.jsx",
    ".spec.js", ".spec.ts", ".spec.tsx", ".spec.jsx", "_spec.rb", "Test.java",
)


def detect_language(path: str) -> str:
    return LANGUAGE_BY_EXT.get(Path(path).suffix.lower(), "unknown")


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if any(part in TEST_DIR_NAMES for part in parts[:-1]):
        return True
    if name.startswith(TEST_FILE_PREFIXES):
        return True
    return name.endswith(TEST_FILE_SUFFIXES)


def is_config_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if name in CONFIG_FILENAMES:
        return True
    if any(part in CONFIG_DIRS for part in parts[:-1]):
        return True
    # A bare .yaml at the root is config; one inside src/ is probably a fixture.
    return name.endswith(CONFIG_SUFFIXES) and len(parts) <= 2


def _git_listed_files(root: Path) -> list[str] | None:
    """One call, gitignore-aware. Returns None outside a git repo or on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]


def _walked_files(root: Path, settings: IndexSettings) -> list[str]:
    excluded = set(settings.exclude_dirs)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in excluded and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root)
        prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/"
        for name in filenames:
            if name.startswith("."):
                continue
            out.append(prefix + name)
            if len(out) >= settings.max_files:
                return out
    return out


def _plain_directory(base: str, directory: str, cache: dict[str, bool]) -> bool:
    """Whether every component of repo-relative ``directory`` is a real directory.

    ``lstat`` on a file follows every component but the last, so a symlinked *parent*
    is invisible to it. `git ls-files --cached` keeps listing ``pkg/mod.py`` after
    ``pkg`` has been replaced by a symlink to somewhere else, so parents are checked too:
    one ``lstat`` per distinct directory, memoised for the scan in ``cache``.
    """
    known = cache.get(directory)
    if known is not None:
        return known
    pending: list[str] = []
    while directory not in cache:
        pending.append(directory)
        directory = directory.rpartition("/")[0]
    plain = cache[directory]
    for current in reversed(pending):
        if plain:
            try:
                plain = stat.S_ISDIR(os.lstat(os.path.join(base, current)).st_mode)
            except (OSError, ValueError):
                plain = False
        cache[current] = plain
    return plain


def _contained_stat(root: Path, rel: str, full: str) -> os.stat_result | None:
    """The full containment guard, for paths that involve a symlink.

    Resolves the candidate before it is stat'ed or read, so a link inside the repository
    cannot smuggle an outside file into the evidence index. Ordinary relative paths keep
    their original spelling as the index key; this is only a containment check.
    """
    if relative_path(root, rel) is None:
        return None
    try:
        st = os.stat(full)
        if not Path(full).resolve(strict=False).is_relative_to(root):
            return None
    except (OSError, RuntimeError, ValueError):
        return None  # deleted between listing and stat, a broken link, or a link loop
    return st


def scan(root: Path, settings: IndexSettings | None = None) -> dict[str, FileRecord]:
    """Return every indexable file, keyed by repo-relative posix path."""
    settings = settings or IndexSettings()
    root = root.resolve()

    paths = _git_listed_files(root)
    from_git = paths is not None
    if paths is None:
        paths = _walked_files(root, settings)

    excluded = set(settings.exclude_dirs)
    max_bytes = settings.max_file_bytes
    max_files = settings.max_files
    base = str(root)
    plain_dirs: dict[str, bool] = {"": True}
    records: dict[str, FileRecord] = {}

    for rel in paths:
        if os.sep != "/":
            rel = rel.replace(os.sep, "/")
        parts = rel.split("/")
        # `git ls-files` respects .gitignore but not our own exclusions (a vendored
        # node_modules can be committed), so filter regardless of source.
        if from_git and any(part in excluded for part in parts[:-1]):
            continue
        # Lexical containment first: `..`, empty and `.` components, absolute paths and
        # NUL bytes never come out of git or the walk, so they are refused unread.
        if any(part in _UNSAFE_PARTS for part in parts) or "\0" in rel or os.path.isabs(rel):
            continue

        full = os.path.join(base, rel)
        # A leading `~` is expanded by `relative_path`, so such a path keeps the
        # canonical check; that keeps the result identical to the per-file resolve.
        if rel[0] != "~" and _plain_directory(base, rel.rpartition("/")[0], plain_dirs):
            try:
                st: os.stat_result | None = os.lstat(full)
            except (OSError, ValueError):
                continue  # deleted between listing and stat
            if stat.S_ISLNK(st.st_mode):
                st = _contained_stat(root, rel, full)
        else:
            st = _contained_stat(root, rel, full)
        if st is None or not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
            continue

        records[rel] = FileRecord(
            path=rel,
            size=st.st_size,
            mtime_ns=st.st_mtime_ns,
            lang=detect_language(rel),
            is_test=is_test_path(rel),
            is_config=is_config_path(rel),
        )
        if len(records) >= max_files:
            break

    return records
