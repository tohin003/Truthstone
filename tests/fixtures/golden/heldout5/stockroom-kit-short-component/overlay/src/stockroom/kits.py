"""Kits: bundles sold as one product but stocked as separate components.

Reserving a kit reserves every component, or nothing at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stockroom.inventory import InsufficientStock, Inventory


@dataclass
class Kit:
    name: str
    components: dict[str, int] = field(default_factory=dict)  # SKU -> units per kit


def reserve_kit(inventory: Inventory, kit: Kit, count: int = 1) -> list[str]:
    """Reserve components for ``count`` kits. Returns one reservation id per component."""
    if count < 1:
        raise ValueError(f"count must be at least 1, got {count!r}")
    reserved: list[str] = []
    try:
        for sku, per_kit in kit.components.items():
            reserved.append(inventory.reserve(sku, per_kit * count))
    except InsufficientStock:
        for reservation_id in reserved:
            inventory.release(reservation_id)
        raise
    return reserved
