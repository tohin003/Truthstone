"""Backorders: order lines that could not be reserved when the order came in.

Backorders for a SKU are filled strictly first-come, first-served: a later, smaller
backorder never jumps ahead of an earlier one that is still waiting for stock, and a new
order's line joins the queue behind any backorder already waiting for its SKU.
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


def fill(inventory: Inventory, queue: list[Backorder]) -> list[tuple[Backorder, str]]:
    """Reserve stock for waiting backorders, oldest first; filled ones leave ``queue``.

    Returns ``(backorder, reservation_id)`` pairs for everything filled.
    """
    filled: list[tuple[Backorder, str]] = []
    blocked: set[str] = set()
    for backorder in list(queue):
        if backorder.sku in blocked:
            continue
        try:
            reservation_id = inventory.reserve(backorder.sku, backorder.quantity)
        except InsufficientStock:
            blocked.add(backorder.sku)
            continue
        queue.remove(backorder)
        filled.append((backorder, reservation_id))
    return filled
