"""Kits: bundles sold as one product but stocked as separate components.

Reserving a kit reserves every component, or nothing at all: a kit is never left partly
reserved. When one component cannot be reserved, the reservations already made for the kit
are released and the error is raised to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stockroom.inventory import InsufficientStock, Inventory


@dataclass
class Kit:
    name: str
    components: dict[str, int] = field(default_factory=dict)  # SKU -> units per kit

    def units(self, count: int = 1) -> dict[str, int]:
        """Units of each component that ``count`` kits need."""
        return {sku: per_kit * count for sku, per_kit in self.components.items()}


def reserve_kit(inventory: Inventory, kit: Kit, count: int = 1) -> list[str]:
    """Reserve components for ``count`` kits. Returns one reservation id per component."""
    if count < 1:
        raise ValueError(f"count must be at least 1, got {count!r}")
    reserved: list[str] = []
    try:
        for sku, quantity in kit.units(count).items():
            reserved.append(inventory.reserve(sku, quantity))
    except InsufficientStock:
        for reservation_id in reserved:
            inventory.release(reservation_id)
        raise
    return reserved
