"""Plain data shared across the package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    """Catalogue data for one SKU, including what reordering needs."""

    sku: str
    name: str
    daily_demand: float = 0.0  # average units sold per day
    lead_time_days: int = 0  # days between placing a purchase order and receiving it
    safety_stock: int = 0
    pack_size: int = 1  # suppliers only sell whole packs


@dataclass(frozen=True)
class Reservation:
    """Stock earmarked for an order. It stays on the shelf until it is fulfilled."""

    reservation_id: str
    sku: str
    quantity: int


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int


@dataclass(frozen=True)
class Order:
    order_id: str
    lines: tuple[OrderLine, ...] = ()
