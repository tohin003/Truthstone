"""The nightly job (another account in the checkout's group) can run the script and write backups/."""

import stat
from pathlib import Path


def check(repo: Path, pristine: Path) -> list[str]:
    problems = []
    script = repo / "scripts" / "backup.sh"
    if not script.is_file():
        problems.append("scripts/backup.sh is missing")
    else:
        mode = script.stat().st_mode
        if not (mode & stat.S_IRGRP and mode & stat.S_IXGRP):
            problems.append("scripts/backup.sh cannot be run by the checkout's group")
    backups = repo / "backups"
    if not backups.is_dir():
        problems.append("backups/ is missing")
    else:
        mode = backups.stat().st_mode
        if not (mode & stat.S_IWGRP and mode & stat.S_IXGRP):
            problems.append("backups/ is not writable by the checkout's group")
    return problems
