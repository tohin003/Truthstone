"""Inventory.transfer moves available stock into another Inventory, all or nothing."""

import pytest

from stockroom.inventory import InsufficientStock, Inventory, UnknownSku


def stocked(levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku, quantity)
    return inventory


def test_moves_stock_to_a_sku_the_destination_already_has():
    north, south = stocked({"W-100": 10}), stocked({"W-100": 3})
    north.transfer("W-100", 4, south)
    assert north.on_hand("W-100") == 6
    assert north.available("W-100") == 6
    assert south.on_hand("W-100") == 7
    assert south.available("W-100") == 7


def test_a_sku_new_to_the_destination_starts_from_zero():
    north, south = stocked({"G-200": 5}), Inventory()
    north.transfer("G-200", 5, south)
    assert north.on_hand("G-200") == 0
    assert south.skus() == ["G-200"]
    assert south.on_hand("G-200") == 5


def test_reserved_stock_stays_behind():
    north, south = stocked({"W-100": 10}), Inventory()
    kept = north.reserve("W-100", 6)
    north.transfer("W-100", 4, south)
    assert north.on_hand("W-100") == 6
    assert north.reserved("W-100") == 6
    assert north.available("W-100") == 0
    assert [r.reservation_id for r in north.reservations()] == [kept]
    assert south.on_hand("W-100") == 4


def test_more_than_available_raises_and_changes_nothing():
    north, south = stocked({"W-100": 10}), stocked({"W-100": 1})
    north.reserve("W-100", 6)
    with pytest.raises(InsufficientStock):
        north.transfer("W-100", 5, south)
    assert north.on_hand("W-100") == 10
    assert north.available("W-100") == 4
    assert south.on_hand("W-100") == 1


def test_unknown_sku_raises_and_changes_nothing():
    north, south = stocked({"W-100": 10}), Inventory()
    with pytest.raises(UnknownSku):
        north.transfer("NOPE", 1, south)
    assert south.skus() == []
    assert north.on_hand("W-100") == 10


@pytest.mark.parametrize("quantity", [0, -2, 1.5])
def test_quantity_must_be_a_positive_whole_number(quantity):
    north, south = stocked({"W-100": 10}), stocked({"W-100": 1})
    with pytest.raises(ValueError):
        north.transfer("W-100", quantity, south)
    assert north.on_hand("W-100") == 10
    assert south.on_hand("W-100") == 1


def test_destination_reservations_are_left_alone():
    north, south = stocked({"W-100": 10}), stocked({"W-100": 2})
    held = south.reserve("W-100", 2)
    north.transfer("W-100", 3, south)
    assert south.reserved("W-100") == 2
    assert south.available("W-100") == 3
    assert [r.reservation_id for r in south.reservations()] == [held]
