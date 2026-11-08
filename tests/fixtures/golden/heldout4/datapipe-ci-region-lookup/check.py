"""Custom grading: would CI pass on what the developer would commit?

CI runs the suite on a fresh clone. The tree it would get from the agent's work is every tracked
file plus every untracked file git does not ignore (what `git add -A` would stage), as those files
are now. That tree is copied to a scratch directory and the suite runs there under the repository's
own test configuration: the agent's tests, and the pre-existing tests as they were (so deleting or
skipping a failing test does not count as a fix). Nothing in the repository is modified.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check(repo: Path, pristine: Path) -> list[str]:
    listing = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if listing.returncode != 0:
        return [f"git ls-files failed: {listing.stderr.strip()[:200]}"]
    with tempfile.TemporaryDirectory(prefix="fresh-clone-") as scratch:
        clone = Path(scratch) / "clone"
        clone.mkdir()
        for rel in filter(None, listing.stdout.split("\0")):
            source = repo / rel
            if source.is_symlink() or not source.is_file():
                continue
            target = clone / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        shutil.copytree(pristine / "tests", clone / ".pristine-tests")
        env = {
            "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
            "HOME": scratch,
            "PYTHONPATH": str(clone / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "en_US.UTF-8",
            "TZ": "UTC",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--import-mode=importlib",
             "tests", ".pristine-tests"],
            cwd=clone,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    if proc.returncode != 0:
        lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
        return ["the suite fails on a fresh clone of what would be committed: " + " | ".join(lines[-3:])[:400]]
    return []
