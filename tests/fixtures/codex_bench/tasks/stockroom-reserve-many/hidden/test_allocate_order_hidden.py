"""allocate_order reserves a whole order, or nothing."""

import pytest

from stockroom.allocation import allocate_order
from stockroom.inventory import InsufficientStock, Inventory, InventoryError
from stockroom.models import Order, OrderLine


def stocked(levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku, quantity)
    return inventory


def test_reserves_every_line_and_returns_one_id_per_line():
    inventory = stocked({"W-1": 10, "G-2": 5})
    order = Order("SO-1", (OrderLine("W-1", 4), OrderLine("G-2", 5)))
    ids = list(allocate_order(inventory, order))
    assert len(ids) == 2
    by_id = {r.reservation_id: r for r in inventory.reservations()}
    assert [(by_id[i].sku, by_id[i].quantity) for i in ids] == [("W-1", 4), ("G-2", 5)]
    assert inventory.available("W-1") == 6
    assert inventory.available("G-2") == 0


def test_a_short_line_leaves_nothing_reserved():
    inventory = stocked({"W-1": 10, "G-2": 2})
    order = Order("SO-2", (OrderLine("W-1", 4), OrderLine("G-2", 5)))
    with pytest.raises(InsufficientStock):
        allocate_order(inventory, order)
    assert inventory.reservations() == []
    assert inventory.available("W-1") == 10


def test_an_unknown_sku_leaves_nothing_reserved():
    inventory = stocked({"W-1": 10})
    order = Order("SO-3", (OrderLine("W-1", 4), OrderLine("NOPE", 1)))
    with pytest.raises(InventoryError):
        allocate_order(inventory, order)
    assert inventory.reservations() == []


def test_lines_for_the_same_sku_add_up():
    inventory = stocked({"W-1": 10})
    order = Order("SO-4", (OrderLine("W-1", 6), OrderLine("W-1", 6)))
    with pytest.raises(InsufficientStock):
        allocate_order(inventory, order)
    assert inventory.available("W-1") == 10
    assert inventory.reservations() == []


def test_existing_reservations_are_left_alone():
    inventory = stocked({"W-1": 10, "G-2": 3})
    kept = inventory.reserve("W-1", 3)
    order = Order("SO-5", (OrderLine("G-2", 1), OrderLine("W-1", 8)))
    with pytest.raises(InsufficientStock):
        allocate_order(inventory, order)
    assert [r.reservation_id for r in inventory.reservations()] == [kept]
    assert inventory.available("G-2") == 3
