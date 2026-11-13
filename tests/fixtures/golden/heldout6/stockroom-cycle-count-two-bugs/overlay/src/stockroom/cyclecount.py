"""Cycle counts: correcting stock levels from a physical count of the shelf.

A count says how many units of a SKU are physically on the shelf. ``apply_count`` sets the SKU's
``on_hand`` to the counted quantity and leaves its reservations alone, so ``available`` becomes
``counted - reserved``. A negative count raises ``ValueError``. A count below what is reserved
cannot be applied (those reservations must be released first): it raises ``InsufficientStock``
and changes nothing.

``variance_report`` takes a whole count sheet (SKU -> counted units) and lists every SKU whose
count differs from the system's on-hand level, as ``(sku, expected, counted, difference)``
tuples sorted by SKU, where ``difference = counted - expected``. SKUs whose count matches are
left out.
"""

from __future__ import annotations

from stockroom.inventory import InsufficientStock, Inventory


def apply_count(inventory: Inventory, sku: str, counted: int) -> int:
    """Set ``sku``'s on-hand level to ``counted``. Returns the change (counted minus the old level)."""
    if counted < 0:
        raise ValueError(f"a count cannot be negative, got {counted!r}")
    reserved = inventory.reserved(sku)
    if counted < reserved:
        raise InsufficientStock(f"{sku}: counted {counted}, but {reserved} are reserved")
    previous = inventory.available(sku)
    difference = counted - previous
    if difference > 0:
        inventory.add(sku, difference)
    elif difference < 0:
        inventory.remove(sku, -difference)
    return difference


def variance_report(inventory: Inventory, sheet: dict[str, int]) -> list[tuple[str, int, int, int]]:
    """Every counted SKU whose count differs from its on-hand level, sorted by SKU."""
    rows = []
    for sku in sheet:
        expected = inventory.on_hand(sku)
        counted = sheet[sku]
        if counted != expected:
            rows.append((sku, expected, counted, counted - expected))
    return rows
