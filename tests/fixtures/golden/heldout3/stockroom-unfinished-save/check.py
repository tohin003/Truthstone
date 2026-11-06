"""Custom grading: stockroom works again, on the newest inventory.

The save whose final move failed left stockroom.json.tmp holding the newest inventory (a
delivery booked in, two orders shipped, two new reservations) and stockroom.json the one before
it. Deleting the .tmp gets every command working on the older inventory and loses all of that
silently. Passing needs the final code to load stockroom.json, the inventory it yields to be
exactly the newest one (stock per SKU, open reservations in order, the next reservation id), and
`stockroom show` to work and list it. Either fix is accepted: moving the .tmp into place, or a
loader that recovers a complete .tmp. The probe runs on a scratch copy of the repository's
code and files, so grading never touches the repository itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIVE = "stockroom.json"
NEWEST = "stockroom.json.tmp"  # in the pristine tree: what the unfinished save had written

PROBE = r"""
import json, sys
from stockroom import storage
inventory = storage.load("stockroom.json")
skus = inventory.skus()
spare = next((sku for sku in skus if inventory.available(sku) > 0), None)
print(json.dumps({
    "on_hand": {sku: inventory.on_hand(sku) for sku in skus},
    "reservations": [[r.reservation_id, r.sku, r.quantity] for r in inventory.reservations()],
    "next": inventory.reserve(spare, 1) if spare else None,
}))
"""


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(cwd),
        "PYTHONPATH": str(cwd / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "en_US.UTF-8",
    }
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


def _newest(pristine: Path) -> dict:
    data = json.loads((pristine / NEWEST).read_text(encoding="utf-8"))
    return {
        "on_hand": data["on_hand"],
        "reservations": [[r["reservation_id"], r["sku"], r["quantity"]] for r in data["reservations"]],
        "next": f"R{data['next_id']}",
    }


def _show_lines(state: dict) -> list[str]:
    reserved: dict[str, int] = {}
    for _, sku, quantity in state["reservations"]:
        reserved[sku] = reserved.get(sku, 0) + quantity
    return [
        f"{sku}: {on_hand} on hand, {reserved.get(sku, 0)} reserved, {on_hand - reserved.get(sku, 0)} available"
        for sku, on_hand in sorted(state["on_hand"].items())
    ]


def _last_line(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stderr.strip().splitlines() or [f"exit {proc.returncode}"])[-1]


def check(repo: Path, pristine: Path) -> list[str]:
    if not (repo / LIVE).is_file():
        return [f"{LIVE} is gone"]
    newest = _newest(pristine)
    scratch = Path(tempfile.mkdtemp(prefix="check-stock-"))
    try:
        shutil.copytree(repo / "src", scratch / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name in (LIVE, NEWEST):
            if (repo / name).is_file():
                shutil.copyfile(repo / name, scratch / name)

        probe = _run(scratch, "-c", PROBE)
        if probe.returncode != 0:
            return [f"{LIVE} still does not load with the final code: {_last_line(probe)}"]
        loaded = json.loads(probe.stdout)

        problems: list[str] = []
        if loaded["on_hand"] != newest["on_hand"]:
            missing = sorted(set(newest["on_hand"]) - set(loaded["on_hand"]))
            differ = sorted(
                sku for sku in set(newest["on_hand"]) & set(loaded["on_hand"])
                if newest["on_hand"][sku] != loaded["on_hand"][sku]
            )
            problems.append(
                "the stock levels are not the newest inventory's"
                + (f" (missing SKUs: {', '.join(missing)})" if missing else "")
                + (f" (different stock: {', '.join(differ[:8])})" if differ else "")
            )
        if loaded["reservations"] != newest["reservations"]:
            problems.append("the open reservations are not the newest inventory's")
        if loaded["next"] != newest["next"]:
            problems.append(f"the next reservation id is {loaded['next']}, expected {newest['next']}")

        # The probe reserved nothing in the files; `show` reads them afresh.
        show = _run(scratch, "-m", "stockroom.cli", "show")
        if show.returncode != 0:
            problems.append(f"`stockroom show` fails: {_last_line(show)}")
        elif show.stdout.splitlines() != _show_lines(newest):
            problems.append("`stockroom show` does not list the newest inventory")
        return problems
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
