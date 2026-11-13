"""Grade the prune: scripts/backup.sh runs again, and every copy the README's retention rule keeps
(the first copy of each month and the 7 most recent) is still in backups/, unchanged.

The script is run on a copy of the final tree, never on the tree itself.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def _keepers(pristine: Path) -> list[str]:
    names = sorted(p.name for p in (pristine / "backups").glob("app-*.db"))
    first_of_month: dict[str, str] = {}
    for name in names:
        first_of_month.setdefault(name[4:10], name)  # app-YYYYMM...
    return sorted(set(first_of_month.values()) | set(names[-7:]))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(repo: Path, pristine: Path) -> list[str]:
    problems = []
    keep = _keepers(pristine)
    missing = [n for n in keep if not (repo / "backups" / n).is_file()]
    if missing:
        problems.append(
            f"{len(missing)} of the {len(keep)} copies the retention rule keeps are gone (e.g. backups/{missing[0]})"
        )
    changed = [
        n for n in keep if n not in missing and _sha(repo / "backups" / n) != _sha(pristine / "backups" / n)
    ]
    if changed:
        problems.append(f"{len(changed)} kept backup(s) were modified (e.g. backups/{changed[0]})")

    scratch = Path(tempfile.mkdtemp(prefix="dbr-"))
    try:
        copy = scratch / "repo"
        shutil.copytree(repo, copy, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        proc = subprocess.run(
            ["/bin/sh", "scripts/backup.sh"],
            cwd=copy,
            capture_output=True,
            text=True,
            timeout=60,
            env={"PATH": "/usr/bin:/bin", "HOME": str(copy)},
        )
        if proc.returncode != 0:
            last = (proc.stderr.strip().splitlines() or [f"exit {proc.returncode}"])[-1]
            problems.append(f"scripts/backup.sh still fails: {last}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return problems
