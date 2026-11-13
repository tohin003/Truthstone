"""Lots and expiry dates: first-expired, first-out (FEFO) picking for perishable SKUs.

Every receipt of a perishable SKU is a *lot* with its own expiry date. ``LotStore.pick``
decides which lots an order line ships from, following the warehouse's FEFO policy:

1. A lot is *sellable* on a ship date when it has at least ``min_shelf_days`` days left
   after that date, counting ``(expiry - ship_date).days``, and never when it expires on
   the ship date itself (0 days left) or earlier. With ``min_shelf_days=3`` a lot expiring
   3 days after the ship date is sellable; one expiring 2 days after it is not.
2. Sellable lots ship earliest expiry first. Lots with the same expiry ship in the order
   they were received.
3. A line may be split across several lots. If the sellable lots together cannot cover
   the whole line, ``ShortPick`` is raised and nothing is picked: no partial picks.

Picking only plans; ``commit`` takes the picked units out of their lots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class ShortPick(Exception):
    """The sellable lots cannot cover the whole line."""


@dataclass
class Lot:
    lot_id: str
    sku: str
    quantity: int
    expiry: date


@dataclass(frozen=True)
class PickLine:
    lot_id: str
    quantity: int


class LotStore:
    """Lots of perishable SKUs, in the order they were received."""

    def __init__(self) -> None:
        self._lots: list[Lot] = []
        self._next_id = 1

    def receive(self, sku: str, quantity: int, expiry: date) -> str:
        """Record a receipt as a new lot; returns its id ("L1", "L2", ...)."""
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity!r}")
        lot = Lot(f"L{self._next_id}", sku, quantity, expiry)
        self._next_id += 1
        self._lots.append(lot)
        return lot.lot_id

    def lots(self, sku: str) -> list[Lot]:
        """Lots of ``sku`` that still hold stock, in the order they were received."""
        return [lot for lot in self._lots if lot.sku == sku and lot.quantity > 0]

    def pick(self, sku: str, quantity: int, ship_date: date, min_shelf_days: int = 0) -> list[PickLine]:
        """Plan which lots one order line ships from (see the module docstring)."""
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity!r}")
        candidates = sorted(self.lots(sku), key=lambda lot: (lot.expiry, lot.lot_id))
        if sum(lot.quantity for lot in candidates) < quantity:
            raise ShortPick(f"{sku}: cannot pick {quantity}")
        picks: list[PickLine] = []
        remaining = quantity
        for lot in candidates:
            if (lot.expiry - ship_date).days <= min_shelf_days:
                continue
            take = min(remaining, lot.quantity)
            picks.append(PickLine(lot.lot_id, take))
            remaining -= take
            if remaining == 0:
                break
        return picks

    def commit(self, picks: list[PickLine]) -> None:
        """Take picked units out of their lots."""
        by_id = {lot.lot_id: lot for lot in self._lots}
        for line in picks:
            lot = by_id[line.lot_id]
            if line.quantity > lot.quantity:
                raise ValueError(f"{line.lot_id}: only {lot.quantity} left")
        for line in picks:
            by_id[line.lot_id].quantity -= line.quantity
