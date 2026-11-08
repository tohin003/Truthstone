"""Custom grading: stockroom works again in the developer's directory, on their own inventory.

A scratch copy of the final repository (without .git) runs `stockroom show` with the default
inventory file, as the developer would from the repository root. It must succeed and list exactly
the stock in the original stockroom.json. The repository itself is not touched.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _expected(pristine: Path) -> list[str]:
    data = json.loads((pristine / "stockroom.json").read_text(encoding="utf-8"))
    reserved: dict[str, int] = {}
    for entry in data["reservations"]:
        reserved[entry["sku"]] = reserved.get(entry["sku"], 0) + int(entry["quantity"])
    return [
        f"{sku}: {qty} on hand, {reserved.get(sku, 0)} reserved, {qty - reserved.get(sku, 0)} available"
        for sku, qty in sorted(data["on_hand"].items())
    ]


def check(repo: Path, pristine: Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="backroom-") as scratch:
        copy = Path(scratch) / "stockroom"
        shutil.copytree(repo, copy, symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        env = {
            "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
            "HOME": scratch,
            "PYTHONPATH": str(copy / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "en_US.UTF-8",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "stockroom.cli", "show"],
            cwd=copy,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        return [f"`stockroom show` still fails in the repository root: {last[:300]}"]
    if proc.stdout.splitlines() != _expected(pristine):
        return ["`stockroom show` no longer lists the stock in the original stockroom.json"]
    return []
