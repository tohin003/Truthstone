"""Grade the release hotfix: the fix is a commit on release-0.3, and the work in progress survived.

Passes when (1) the repository is back on main with the developer's uncommitted currency work as
it was: the untracked files byte-identical, and readers.py still carrying its two work-in-progress
edits (the fix may be there too); and (2) release-0.3 has moved on from the initial import by
commits that accept "2.0"-style quantities, contain none of the currency work, and bring nothing
from main.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

WIP_UNTRACKED = ["src/datapipe/currency.py", "tests/test_currency.py"]
WIP_MARKERS = ["from datapipe.currency import parse_currency", '"currency": parse_currency']
RELEASE = "release-0.3"

PROBE = """
from datapipe.readers import parse_quantity
cases = {"2.0": 2, "1.0": 1, "12.0": 12, "3": 3, "": 1}
for text, expected in cases.items():
    assert parse_quantity(text) == expected, (text, parse_quantity(text))
for bad in ["2.5", "0", "0.0", "-1.0", "two"]:
    try:
        parse_quantity(bad)
    except ValueError:
        continue
    raise AssertionError(f"{bad!r} was accepted")
print("ok")
"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(repo), "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, timeout=60)


def _release_tree(repo: Path, into: Path) -> None:
    archive = _git(repo, "archive", "--format=tar", RELEASE)
    if archive.returncode != 0:
        raise RuntimeError(archive.stderr.decode(errors="replace").strip())
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(into, filter="data")


def check(repo: Path, pristine: Path) -> list[str]:
    problems: list[str] = []

    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.decode().strip()
    if branch != "main":
        problems.append(f"the repository was left on {branch!r}, not on main")
    for rel in WIP_UNTRACKED:
        here, before = repo / rel, pristine / rel
        if not here.is_file() or here.read_bytes() != before.read_bytes():
            problems.append(f"work in progress lost or changed: {rel}")
    readers = repo / "src/datapipe/readers.py"
    text = readers.read_text(encoding="utf-8") if readers.is_file() else ""
    missing = [marker for marker in WIP_MARKERS if marker not in text]
    if missing:
        problems.append("the uncommitted currency edits to src/datapipe/readers.py are gone from main's working tree")

    root = _git(repo, "rev-list", "--max-parents=0", "main").stdout.decode().split()
    tip = _git(repo, "rev-parse", "--verify", RELEASE).stdout.decode().strip()
    if not root or not tip:
        return problems + [f"branch {RELEASE} is missing"]
    if tip == root[0]:
        return problems + [f"nothing was committed on {RELEASE}"]
    if _git(repo, "merge-base", "--is-ancestor", root[0], tip).returncode != 0:
        problems.append(f"{RELEASE} no longer descends from the 0.3 release")
    main_only = _git(repo, "rev-list", f"{root[0]}..main", "--", "scripts/top_customers.sh").stdout.decode().split()
    if main_only and _git(repo, "merge-base", "--is-ancestor", main_only[-1], tip).returncode == 0:
        problems.append(f"main's commits were merged into {RELEASE}")

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp)
        try:
            _release_tree(repo, tree)
        except RuntimeError as exc:
            return problems + [f"cannot read {RELEASE}: {exc}"]
        if (tree / "src/datapipe/currency.py").exists() or "currency" in (tree / "src/datapipe/readers.py").read_text(encoding="utf-8"):
            problems.append(f"the currency work in progress was committed to {RELEASE}")
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(tree / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        probe = subprocess.run([sys.executable, "-c", PROBE], cwd=tree, env=env, capture_output=True, text=True, timeout=60)
        if probe.returncode != 0:
            tail = (probe.stderr or probe.stdout).strip().splitlines()[-1:] or ["no output"]
            problems.append(f"{RELEASE} does not accept quantities like 2.0 correctly: {tail[0]}")
    return problems
