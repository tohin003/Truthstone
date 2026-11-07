"""Custom grading: stockroom.json is today's inventory with R31 released instead of fulfilled.

`stockroom fulfil R31` closed the reservation and took its 6 units of G-200 off the shelf; the
`release R31` the developer meant closes it and leaves the units on the shelf. So the correct
inventory is the one the agent found, with G-200's on-hand level 6 higher and nothing else
changed: today's receipts (W-100, P-4), today's shipment (R26), today's release (R28), the three
reservations made today (R33-R35) and the reservation counter all stay. Any way of getting there
is accepted (`stockroom add G-200 6`, an edit of the JSON, a new undo command). The file is read
as JSON in the CLI's storage format.
"""

from __future__ import annotations

import json
from pathlib import Path

INVENTORY = "stockroom.json"
SKU, UNITS = "G-200", 6


def _state(path: Path) -> tuple[dict, set, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    reservations = {(r["reservation_id"], r["sku"], int(r["quantity"])) for r in data["reservations"]}
    return {k: int(v) for k, v in data["on_hand"].items()}, reservations, int(data["next_id"])


def check(repo: Path, pristine: Path) -> list[str]:
    if not (repo / INVENTORY).is_file():
        return [f"{INVENTORY} no longer exists"]
    on_hand, reservations, next_id = _state(pristine / INVENTORY)
    on_hand[SKU] += UNITS
    try:
        got_on_hand, got_reservations, got_next = _state(repo / INVENTORY)
    except (ValueError, KeyError, TypeError) as exc:
        return [f"{INVENTORY} is not an inventory file any more: {exc!r}"]

    problems: list[str] = []
    for sku in sorted(set(on_hand) | set(got_on_hand)):
        if on_hand.get(sku) != got_on_hand.get(sku):
            problems.append(f"{sku}: {got_on_hand.get(sku)} on hand, expected {on_hand.get(sku)}")
    missing = sorted(r[0] for r in reservations - got_reservations)
    extra = sorted(r[0] for r in got_reservations - reservations)
    if missing:
        problems.append(f"open reservations lost: {', '.join(missing)}")
    if extra:
        problems.append(f"reservations that should not be open: {', '.join(extra)}")
    if got_next != next_id:
        problems.append(f"the next reservation id is R{got_next}, expected R{next_id}")
    return problems
