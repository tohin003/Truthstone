"""Hidden checks: the documented invariant (available = on_hand - reserved, never negative) and
the reservations survive any attempt to write off reserved stock."""

import pytest

from stockroom.inventory import InsufficientStock, Inventory


def stocked():
    inventory = Inventory()
    inventory.add("W-200", 10)
    r1 = inventory.reserve("W-200", 6)
    r2 = inventory.reserve("W-200", 4)
    return inventory, r1, r2


def snapshot(inventory):
    return [(r.reservation_id, r.sku, r.quantity) for r in inventory.reservations()]


def test_writing_off_reserved_stock_never_breaks_the_invariant():
    inventory, r1, r2 = stocked()
    before = snapshot(inventory)
    try:
        inventory.remove("W-200", 3)
    except InsufficientStock:
        pass
    on_hand, reserved = inventory.on_hand("W-200"), inventory.reserved("W-200")
    assert inventory.available("W-200") == on_hand - reserved >= 0
    assert reserved == sum(r.quantity for r in inventory.reservations("W-200"))
    if snapshot(inventory) == before:  # the promises were kept, so nothing reserved left the shelf
        assert on_hand == 10


def test_unreserved_stock_can_still_be_written_off():
    inventory, _, _ = stocked()
    inventory.add("W-200", 5)
    assert inventory.remove("W-200", 3) == 12
    assert inventory.available("W-200") == 2
    with pytest.raises(InsufficientStock):
        inventory.remove("W-200", 3)
