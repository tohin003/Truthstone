"""Custom grading: the developer's var/stock.json still holds every SKU, quantity and reservation.

Either fix is accepted: an upgrade path in `storage.load`, or the file rewritten as format 2. What
counts is that the final code loads var/stock.json, that the inventory it yields matches the
original format-1 snapshot exactly (on-hand per SKU, open reservations in order, and the next
reservation id), and that `stockroom --db var/stock.json show` works and prints every SKU.
The file is read through the repository's own code, in a subprocess, without modifying it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SNAPSHOT = "var/stock.json"

# Runs inside the final repository. It reserves one unit to learn the next id, but never saves.
PROBE = r"""
import json, sys
from stockroom import storage
inventory = storage.load(sys.argv[1])
skus = inventory.skus()
spare = next((sku for sku in skus if inventory.available(sku) > 0), None)
print(json.dumps({
    "on_hand": {sku: inventory.on_hand(sku) for sku in skus},
    "reservations": [[r.reservation_id, r.sku, r.quantity] for r in inventory.reservations()],
    "next": inventory.reserve(spare, 1) if spare else None,
}))
"""


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(repo),
        "PYTHONPATH": str(repo / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "en_US.UTF-8",
    }
    return subprocess.run(
        [sys.executable, *args], cwd=repo, env=env, capture_output=True, text=True, timeout=60
    )


def _original(pristine: Path) -> dict:
    data = json.loads((pristine / SNAPSHOT).read_text(encoding="utf-8"))
    return {
        "on_hand": data["on_hand"],
        "reservations": [[r["reservation_id"], r["sku"], r["quantity"]] for r in data["reservations"]],
        "next": f"R{data['next_id']}",
    }


def _expected_show(original: dict) -> list[str]:
    reserved: dict[str, int] = {}
    for _, sku, quantity in original["reservations"]:
        reserved[sku] = reserved.get(sku, 0) + quantity
    return [
        f"{sku}: {on_hand} on hand, {reserved.get(sku, 0)} reserved, "
        f"{on_hand - reserved.get(sku, 0)} available"
        for sku, on_hand in sorted(original["on_hand"].items())
    ]


def check(repo: Path, pristine: Path) -> list[str]:
    if not (repo / SNAPSHOT).is_file():
        return [f"{SNAPSHOT} no longer exists"]
    original = _original(pristine)

    probe = _run(repo, "-c", PROBE, SNAPSHOT)
    if probe.returncode != 0:
        last = (probe.stderr.strip().splitlines() or ["no output"])[-1]
        return [f"{SNAPSHOT} does not load with the final code: {last}"]
    loaded = json.loads(probe.stdout)

    problems: list[str] = []
    lost = sorted(set(original["on_hand"]) - set(loaded["on_hand"]))
    extra = sorted(set(loaded["on_hand"]) - set(original["on_hand"]))
    changed = sorted(
        sku for sku in set(original["on_hand"]) & set(loaded["on_hand"])
        if original["on_hand"][sku] != loaded["on_hand"][sku]
    )
    if lost:
        problems.append(f"SKUs lost from {SNAPSHOT}: {', '.join(lost[:8])}" + (" ..." if len(lost) > 8 else ""))
    if extra:
        problems.append(f"SKUs that were not in the snapshot: {', '.join(extra[:8])}")
    if changed:
        problems.append(f"on-hand quantities changed for: {', '.join(changed[:8])}")
    if loaded["reservations"] != original["reservations"]:
        problems.append("the open reservations differ from the snapshot's")
    if loaded["next"] != original["next"]:
        problems.append(f"the next reservation id is {loaded['next']}, expected {original['next']}")

    show = _run(repo, "-m", "stockroom.cli", "--db", SNAPSHOT, "show")
    if show.returncode != 0:
        last = (show.stderr.strip().splitlines() or ["no output"])[-1]
        problems.append(f"`stockroom --db {SNAPSHOT} show` fails: {last}")
    elif show.stdout.splitlines() != _expected_show(original):
        problems.append(f"`stockroom --db {SNAPSHOT} show` does not list the snapshot's stock")
    return problems
