"""Path-boundary helpers for repository evidence and mutation handling.

Hook payloads are host-provided data.  A path in one is not automatically a path in the
repository whose ``cwd`` arrived with the payload.  This module provides the one canonical
conversion used by the index and evidence engine so absolute paths, ``..`` traversal, and
symlinks pointing outside the workspace cannot turn an evidence lookup into an arbitrary
filesystem read.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

_UNSAFE_PARTS = ("", ".", "..")


def _fold(name: str) -> str:
    """The spelling a case-insensitive volume compares: case- and normalisation-blind."""
    return unicodedata.normalize("NFC", name).casefold()


def _on_disk_spelling(base: Path, parts: tuple[str, ...]) -> tuple[str, ...]:
    """``parts`` (below ``base``) respelled as the directory entries actually are.

    The scanner keys the index by the tree's own spelling, so ``SRC/A.py`` must come back
    as ``src/a.py`` to name the indexed file. A component with no unique case-insensitive
    match (a file about to be created) keeps the given spelling from there on.
    """
    out: list[str] = []
    current = base
    for index, part in enumerate(parts):
        try:
            entries = os.listdir(current)
        except OSError:
            return (*out, *parts[index:])
        if part not in entries:
            wanted = _fold(part)
            matches = [entry for entry in entries if _fold(entry) == wanted]
            if len(matches) != 1:
                return (*out, *parts[index:])
            part = matches[0]
        out.append(part)
        current = current / part
    return tuple(out)


def _same_directory_relative(base: Path, path: Path) -> Path | None:
    """``path`` relative to ``base`` when it spells ``base`` differently (R18).

    On a case-insensitive volume (APFS and HFS+ by default, NTFS) ``/x/REPO/a.py`` names
    ``/x/Repo/a.py``, yet ``relative_to`` compares spellings and calls it outside: the
    edit went untracked. Only a head that folds to ``base``'s own spelling is considered,
    and it must then be the *same directory* on disk (``samefile``), so on a
    case-sensitive volume a differently-cased sibling stays outside. ``path`` must be
    canonical (resolved): containment through symlinks and ``..`` was already decided.
    """
    count = len(base.parts)
    if len(path.parts) <= count:
        return None
    head = path.parts[:count]
    if [_fold(part) for part in head] != [_fold(part) for part in base.parts]:
        return None
    try:
        if not os.path.samefile(Path(*head), base):
            return None
    except (OSError, ValueError):
        return None
    rest = path.parts[count:]
    if any(part in _UNSAFE_PARTS for part in rest):
        return Path(*rest)  # discarded by the caller, which then uses the canonical form
    return Path(*_on_disk_spelling(base, rest))


def _inside(base: Path, path: Path) -> Path | None:
    """``path`` relative to ``base``, or ``None`` when it is not below it."""
    try:
        return path.relative_to(base)
    except ValueError:
        return _same_directory_relative(base, path)


def relative_path(root: Path, raw: str | Path) -> str | None:
    """Return a canonical repo-relative POSIX path, or ``None`` if it escapes ``root``.

    ``Path.resolve(strict=False)`` canonicalises existing symlink components while still
    allowing a path for a file that is about to be created.  Containment is checked after
    that canonicalisation, so a symlink such as ``repo/out -> /tmp`` cannot be used to
    read or index ``/tmp/secret.py``.  Callers still need normal filesystem error handling
    because the path may disappear or change between this check and the subsequent read.

    A path that spells the root differently but names the same directory, such as a
    case variant on a case-insensitive volume, is inside; it comes back in the tree's
    own spelling (R18).
    """

    if not isinstance(raw, (str, Path)):
        return None
    try:
        base = Path(root).expanduser().resolve(strict=False)
        candidate = Path(raw).expanduser()
        # Relative paths are interpreted exactly as paths inside the workspace.  Absolute
        # paths are accepted only when their canonical target is inside that workspace.
        absolute = base / candidate if not candidate.is_absolute() else candidate
        canonical = absolute.resolve(strict=False)
        canonical_relative = _inside(base, canonical)
        if canonical_relative is None:
            return None

        # Preserve a safe path's repository spelling.  The scanner stores paths exactly
        # as they appear in the tree, so canonicalising an internal symlink to its target
        # here would make ``normalize("link.py")`` disagree with the ``link.py`` index
        # key.  Paths containing ``..`` are the exception: their operating-system
        # resolution can depend on a preceding symlink, so use the canonical spelling.
        lexical_relative = _inside(base, absolute) or canonical_relative
        relative = (
            canonical_relative
            if any(part in _UNSAFE_PARTS for part in lexical_relative.parts)
            else lexical_relative
        )
    except (OSError, RuntimeError, ValueError):
        # RuntimeError covers symlink loops; ValueError covers non-relative paths on
        # platforms with different drives.  Both mean "no evidence", never a filesystem
        # access outside the guarded repository.
        return None

    rendered = relative.as_posix()
    # ``relative_to`` returns ``.`` for the root itself.  A root is not a file path and
    # accepting it would make refresh/read callers inspect the directory unexpectedly.
    return None if rendered in ("", ".") else rendered
