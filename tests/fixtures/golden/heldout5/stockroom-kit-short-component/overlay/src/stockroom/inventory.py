"""Stock levels and reservations.

``on_hand`` is what is physically on the shelf. A reservation earmarks stock for an
order without moving it, and ``available`` is what can still be promised:
``on_hand - reserved``. Neither reserving nor writing stock off may take ``available``
below zero; both raise ``InsufficientStock`` instead.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from stockroom.models import Reservation


class InventoryError(Exception):
    """Base class for inventory errors."""


class UnknownSku(InventoryError):
    """The SKU has never been stocked."""


class InsufficientStock(InventoryError):
    """Not enough stock is available for the request."""


class UnknownReservation(InventoryError):
    """No open reservation has this id."""


class Inventory:
    """Stock on hand and open reservations, per SKU."""

    def __init__(self) -> None:
        self._on_hand: dict[str, int] = {}
        self._reserved: dict[str, int] = {}
        self._reservations: dict[str, Reservation] = {}
        self._next_id = 1

    # -- levels --------------------------------------------------------------------

    def skus(self) -> list[str]:
        return sorted(self._on_hand)

    def on_hand(self, sku: str) -> int:
        try:
            return self._on_hand[sku]
        except KeyError:
            raise UnknownSku(sku) from None

    def reserved(self, sku: str) -> int:
        self.on_hand(sku)  # unknown SKUs raise
        return self._reserved.get(sku, 0)

    def available(self, sku: str) -> int:
        return self.on_hand(sku) - self.reserved(sku)

    # -- stock movements -----------------------------------------------------------

    def add(self, sku: str, quantity: int) -> int:
        """Receive stock; a new SKU starts from zero. Returns the new on-hand level."""
        _check_quantity(quantity)
        self._on_hand[sku] = self._on_hand.get(sku, 0) + quantity
        return self._on_hand[sku]

    def remove(self, sku: str, quantity: int) -> int:
        """Write stock off (damaged, lost, counted short). Returns the new on-hand level.

        Raises InsufficientStock if ``quantity`` is more than is available: reserved
        stock cannot be written off until its reservation is released.
        """
        _check_quantity(quantity)
        available = self.available(sku)
        if quantity > available:
            raise InsufficientStock(f"{sku}: cannot remove {quantity}, {available} available")
        self._on_hand[sku] -= quantity
        return self._on_hand[sku]

    # -- reservations ----------------------------------------------------------------

    def reserve(self, sku: str, quantity: int) -> str:
        """Earmark ``quantity`` units of ``sku``. Returns the new reservation's id."""
        _check_quantity(quantity)
        available = self.available(sku)
        if quantity > available:
            raise InsufficientStock(f"{sku}: cannot reserve {quantity}, {available} available")
        reservation = Reservation(f"R{self._next_id}", sku, quantity)
        self._next_id += 1
        self._reservations[reservation.reservation_id] = reservation
        self._reserved[sku] = self._reserved.get(sku, 0) + quantity
        return reservation.reservation_id

    def release(self, reservation_id: str) -> Reservation:
        """Cancel a reservation; its stock becomes available again."""
        try:
            return self._reservations.pop(reservation_id)
        except KeyError:
            raise UnknownReservation(reservation_id) from None

    def fulfil(self, reservation_id: str) -> Reservation:
        """Ship a reservation: its stock leaves the shelf."""
        reservation = self._close(reservation_id)
        self._on_hand[reservation.sku] -= reservation.quantity
        return reservation

    def reservations(self, sku: str | None = None) -> list[Reservation]:
        """Open reservations, oldest first, optionally for one SKU."""
        return [r for r in self._reservations.values() if sku is None or r.sku == sku]

    def _close(self, reservation_id: str) -> Reservation:
        try:
            reservation = self._reservations.pop(reservation_id)
        except KeyError:
            raise UnknownReservation(reservation_id) from None
        self._reserved[reservation.sku] -= reservation.quantity
        return reservation

    # -- persistence -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "on_hand": dict(sorted(self._on_hand.items())),
            "reservations": [asdict(r) for r in self._reservations.values()],
            "next_id": self._next_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Inventory:
        inventory = cls()
        for sku, quantity in data.get("on_hand", {}).items():
            inventory._on_hand[sku] = int(quantity)
        for entry in data.get("reservations", []):
            reservation = Reservation(**entry)
            inventory._reservations[reservation.reservation_id] = reservation
            inventory._reserved[reservation.sku] = (
                inventory._reserved.get(reservation.sku, 0) + reservation.quantity
            )
        inventory._next_id = int(data.get("next_id", 1))
        return inventory


def _check_quantity(quantity: int) -> None:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError(f"quantity must be a positive whole number, got {quantity!r}")
