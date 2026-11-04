"""What a file was before the task changed it, and what its code is now (G2b).

Two refinements of the verification timeline (G2a) need to compare a file with an earlier
version of itself, and both are cheap enough only if they stay narrow:

* **A reverted file is no change** (Pebble ``unstage``, ``guard.py:1060-1091``; same owner,
  Apache-2.0). At a file's first change in a task, ``Guard._record_parse_baseline`` sees
  it as it was; ``capture`` keeps a SHA-256 of its bytes (or that it did not exist). At
  Stop a touched file whose bytes are back to that digest — or that is absent again — has
  not changed. The baseline is the file as the task found it, never git HEAD: the
  developer's own uncommitted edits are not the agent's to have "reverted".
* **A comment-only edit keeps a pass** (G2a's known false block: all three local "stale"
  claims D1 inspected were 0-code-line edits). A Python file's code is fingerprinted with
  ``ast.dump`` without positions, so comments, blank lines and formatting do not move it;
  docstrings do (they can be doctests). ``remember_pass`` records the fingerprint of every
  touched Python file when a passing run is recorded; at Stop a file changed after that
  pass whose fingerprint is unchanged is not stale. A file first changed after the pass is
  compared with its baseline instead, which is what the pass ran on.

* **What the change removed** (M2, M4, the unread-config check). The Stop-time integrity
  checks compare a file as the task found it with the file now: a documented rule removed,
  a test weakened, a config key added. So the baseline also keeps the file's text,
  compressed, for text files up to ``MAX_TEXT_BYTES``. Never git HEAD, for the same reason
  as above: the developer's uncommitted edits are not the agent's.

Bounded: only touched files, digests up to ``MAX_DIGEST_BYTES``, fingerprints only for
Python files up to ``MAX_AST_BYTES``, text up to ``MAX_TEXT_BYTES`` per file and
``MAX_TASK_TEXT_BYTES`` (compressed) per task. Nothing here raises; an unreadable file has
no digest and no fingerprint, which only means "changed", as before.
"""

from __future__ import annotations

import ast
import hashlib
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from truthstone.repo.paths import relative_path

if TYPE_CHECKING:
    from truthstone.core.taskstate import TaskState

__all__ = [
    "FileBaseline",
    "before_text",
    "capture",
    "code_unchanged",
    "content_digest",
    "fingerprint",
    "remember_pass",
    "reverted",
]

MAX_DIGEST_BYTES = 4_000_000  # larger files keep no digest: they can never count as reverted
MAX_AST_BYTES = 1_000_000  # larger Python files are never fingerprinted
PASS_HISTORY = 4  # fingerprints kept per file, one per passing run
MAX_TEXT_BYTES = 512_000  # larger files keep no text: the integrity checks stay silent on them
MAX_TASK_TEXT_BYTES = 8_000_000  # compressed text kept per task, at most


@dataclass(frozen=True, slots=True)
class FileBaseline:
    """A file as the task found it, taken just before the task's first change to it."""

    exists: bool
    digest: str | None  # SHA-256 of the bytes; None when absent, unreadable or too large
    seq: int  # the task's sequence number when it was taken (G2a timeline)
    # The task had already recorded a change to the file (a shell command, say), so this
    # is not the file as the task found it: it is never used as one.
    changed_before: bool = False
    fingerprint: str | None = None  # Python only: the code, without comments or positions
    parses: bool | None = None  # Python only: whether it parsed (G15), when it was read
    # The file's text, zlib-compressed UTF-8, when it is text and small enough (M2, M4).
    text: bytes | None = None


def _resolve(root: Path, path: str) -> Path | None:
    safe = relative_path(root, path)
    if safe is None:
        return None
    full = root / safe
    try:
        if not full.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
            return None
    except (OSError, RuntimeError):
        return None
    return full


def _read(root: Path, path: str, limit: int) -> tuple[bool, bytes | None]:
    """(exists, bytes) — bytes is None when the file is absent, unreadable or over ``limit``."""
    full = _resolve(root, path)
    if full is None:
        return False, None
    try:
        if not full.is_file():
            return full.exists(), None
        if full.stat().st_size > limit:
            return True, None
        return True, full.read_bytes()
    except OSError:
        return True, None


def _fingerprint_source(data: bytes) -> tuple[bool | None, str | None]:
    """(parses, fingerprint) of Python source bytes."""
    if len(data) > MAX_AST_BYTES:
        return None, None
    try:
        tree = ast.parse(data.decode("utf-8", errors="replace"))
    except SyntaxError:
        return False, None
    except (ValueError, RecursionError, MemoryError):
        return None, None
    try:
        dumped = ast.dump(tree, annotate_fields=True, include_attributes=False)
    except (ValueError, RecursionError, MemoryError):
        return True, None
    return True, hashlib.sha256(dumped.encode("utf-8", errors="replace")).hexdigest()


def _is_python(path: str) -> bool:
    return path.endswith((".py", ".pyi"))


def content_digest(root: Path, path: str) -> tuple[bool, str | None]:
    """(exists, SHA-256 of its bytes) for a file as it is on disk now."""
    exists, data = _read(root, path, MAX_DIGEST_BYTES)
    return exists, (hashlib.sha256(data).hexdigest() if data is not None else None)


def fingerprint(root: Path, path: str) -> str | None:
    """The code of a Python file as it is now, or None (not Python, missing, too large or
    unparsable)."""
    if not _is_python(path):
        return None
    _, data = _read(root, path, MAX_AST_BYTES)
    return _fingerprint_source(data)[1] if data is not None else None


def capture(
    root: Path, path: str, seq: int, changed_before: bool = False, text_budget: int = MAX_TASK_TEXT_BYTES
) -> FileBaseline:
    """The file before the task's first change to it. Never raises. ``text_budget`` is the
    compressed text the task may still keep (``MAX_TASK_TEXT_BYTES`` minus what it holds)."""
    try:
        exists, data = _read(root, path, MAX_DIGEST_BYTES)
        digest = hashlib.sha256(data).hexdigest() if data is not None else None
        parses = code = None
        if data is not None and _is_python(path):
            parses, code = _fingerprint_source(data)
        text = _compress(data) if data is not None and len(data) <= MAX_TEXT_BYTES else None
        if text is not None and len(text) > text_budget:
            text = None
        return FileBaseline(exists, digest, seq, changed_before, code, parses, text)
    except Exception:  # noqa: BLE001 - a baseline only sharpens the gate; never a failure
        return FileBaseline(True, None, seq, True)


def _compress(data: bytes) -> bytes | None:
    if b"\x00" in data[:8192]:
        return None  # binary: no text to compare
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return zlib.compress(data, 6)


def text_bytes(state: TaskState) -> int:
    """Compressed baseline text the task holds."""
    return sum(len(base.text) for base in state.file_baselines.values() if base.text is not None)


def before_text(state: TaskState, path: str) -> str | None:
    """The file's text as the task found it, or None: never captured, created by the task,
    first changed by a shell command (so not as the task found it), binary or too large."""
    base = state.file_baselines.get(path)
    if base is None or base.changed_before or not base.exists or base.text is None:
        return None
    try:
        return zlib.decompress(base.text).decode("utf-8")
    except (zlib.error, UnicodeDecodeError):
        return None


def current_text(root: Path, path: str) -> tuple[bool, str | None]:
    """(exists, text) of a file as it is now; text None when unreadable, binary or large."""
    exists, data = _read(root, path, MAX_TEXT_BYTES)
    if data is None or b"\x00" in data[:8192]:
        return exists, None
    try:
        return exists, data.decode("utf-8")
    except UnicodeDecodeError:
        return exists, None


def reverted(state: TaskState, root: Path) -> set[str]:
    """Changed files that are back to how the task found them (or absent again)."""
    out: set[str] = set()
    for path in state.touched_files | state.deleted_files:
        base = state.file_baselines.get(path)
        if base is None or base.changed_before:
            continue
        if _back_to(base, *content_digest(root, path)):
            out.add(path)
    return out


def _back_to(base: FileBaseline, exists: bool, digest: str | None) -> bool:
    if not base.exists:
        return not exists  # created, then removed again
    return exists and base.digest is not None and digest == base.digest


def remember_pass(state: TaskState, root: Path, seq: int | None) -> None:
    """Fingerprint every touched Python file for the passing run at ``seq``.

    A file not changed since the last pass that fingerprinted it keeps that fingerprint
    without being read again.
    """
    if seq is None:
        return
    for path in sorted(state.touched_files - state.deleted_files):
        if not _is_python(path):
            continue
        history = state.pass_fingerprints.setdefault(path, {})
        last = max(history) if history else None
        if last is not None and state.last_change_seq.get(path, 0) < last:
            history[seq] = history[last]
        else:
            current = fingerprint(root, path)
            if current is None:
                continue
            history[seq] = current
        for old in sorted(history)[:-PASS_HISTORY]:
            del history[old]


def code_unchanged(state: TaskState, root: Path, path: str, seq: int | None) -> bool:
    """Whether a Python file's code is what the passing run at ``seq`` ran on."""
    if seq is None or not _is_python(path):
        return False
    then = state.pass_fingerprints.get(path, {}).get(seq)
    if then is None:
        # First changed after that run: the run saw the file as the task found it.
        base = state.file_baselines.get(path)
        if base is not None and not base.changed_before and base.seq >= seq:
            then = base.fingerprint
    if then is None:
        return False
    return fingerprint(root, path) == then
