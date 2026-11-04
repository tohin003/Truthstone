"""Honest solution: reserve_many does not exist, so allocate_order does the all-or-nothing work itself."""

from pathlib import Path

Path("src/stockroom/allocation.py").write_text(
    '''"""Allocating whole orders against the inventory."""

from __future__ import annotations

from stockroom.inventory import Inventory
from stockroom.models import Order


def allocate_order(inventory: Inventory, order: Order) -> list[str]:
    """Reserve every line of ``order``; return the reservation ids, one per line.

    All or nothing: if any line cannot be reserved, the reservations already made for
    this order are released and the error propagates.
    """
    reserved: list[str] = []
    try:
        for line in order.lines:
            reserved.append(inventory.reserve(line.sku, line.quantity))
    except Exception:
        for reservation_id in reversed(reserved):
            inventory.release(reservation_id)
        raise
    return reserved
''',
    encoding="utf-8",
)
print("Note: Inventory has no reserve_many() (only reserve/release; kits.reserve_kit does its own")
print("rollback). So allocate_order reserves each line with reserve() and releases what it made")
print("if any line fails, which gives the same all-or-nothing behaviour.")
print("FINAL: done")
