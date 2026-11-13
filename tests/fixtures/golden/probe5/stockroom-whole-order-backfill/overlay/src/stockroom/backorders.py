"""Backorders: order lines that could not be reserved when the order came in.

Backorders for a SKU are filled strictly first-come, first-served: a later, smaller
backorder never jumps ahead of an earlier one that is still waiting for stock, and a new
order's line joins the queue behind any backorder already waiting for its SKU.

Since 0.7.0 (#71) the waiting lines of one order are filled together: ``fill`` reserves stock
for every waiting line of an order, or for none of them, so a customer never receives half an
order. An order that cannot be filled in full yet keeps its place for each of its SKUs: no later
order's backorder for any of those SKUs is filled before it. Orders that need none of its SKUs
are filled as stock allows.
"""

from __future__ import annotations

from dataclasses import dataclass

from stockroom.inventory import InsufficientStock, Inventory
from stockroom.models import Order


@dataclass(frozen=True)
class Backorder:
    order_id: str
    sku: str
    quantity: int


def promise(inventory: Inventory, order: Order, queue: list[Backorder]) -> list[str]:
    """Reserve each line of ``order`` that stock allows and backorder the others.

    A line is reserved in full or not at all. Returns the reservation ids made now.
    """
    reserved: list[str] = []
    waiting = {backorder.sku for backorder in queue}
    for line in order.lines:
        if line.sku not in waiting:
            try:
                reserved.append(inventory.reserve(line.sku, line.quantity))
                continue
            except InsufficientStock:
                pass
        queue.append(Backorder(order.order_id, line.sku, line.quantity))
        waiting.add(line.sku)
    return reserved


def _orders(queue: list[Backorder]) -> list[str]:
    """Order ids in the order their first backorder joined the queue."""
    seen: dict[str, None] = {}
    for backorder in queue:
        seen.setdefault(backorder.order_id, None)
    return list(seen)


def fill(inventory: Inventory, queue: list[Backorder]) -> list[tuple[Backorder, str]]:
    """Reserve stock for waiting orders, oldest first; filled backorders leave ``queue``.

    Every waiting line of an order is reserved, or none is. Returns ``(backorder,
    reservation_id)`` pairs for everything filled, in queue order.
    """
    filled: list[tuple[Backorder, str]] = []
    blocked: set[str] = set()
    for order_id in _orders(queue):
        lines = [backorder for backorder in queue if backorder.order_id == order_id]
        reserved: list[tuple[Backorder, str]] = []
        try:
            for backorder in lines:
                if backorder.sku in blocked:
                    raise InsufficientStock(f"{backorder.sku}: an earlier order is waiting")
                reserved.append((backorder, inventory.reserve(backorder.sku, backorder.quantity)))
        except InsufficientStock:
            for _, reservation_id in reserved:
                inventory.release(reservation_id)
            blocked.add(backorder.sku)
            continue
        for backorder, _ in reserved:
            queue.remove(backorder)
        filled.extend(reserved)
    return filled
