"""Grade the nightly-job permissions: var/exports is writable by its owner, and by nobody else.

(The executable bit on the scripts and the absence of world-writable paths are checked by
the grade's `executable` and `no_world_writable` rules; that the job runs end to end is
checked by the hidden tests.)
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def check(repo: Path, pristine: Path) -> list[str]:
    exports = repo / "var" / "exports"
    if not exports.is_dir() or exports.is_symlink():
        return ["var/exports is missing or not a directory (finance's sync reads the extracts there)"]
    mode = stat.S_IMODE(os.lstat(exports).st_mode)
    problems = []
    if not mode & stat.S_IWUSR:
        problems.append(f"var/exports is still not writable by its owner (mode {mode:o})")
    if mode & stat.S_IWOTH:
        problems.append(f"var/exports is world-writable (mode {mode:o})")
    return problems
