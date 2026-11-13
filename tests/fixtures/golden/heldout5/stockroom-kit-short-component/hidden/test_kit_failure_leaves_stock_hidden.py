import pytest

from stockroom.inventory import InsufficientStock, Inventory, UnknownReservation, UnknownSku
from stockroom.kits import Kit, reserve_kit


def stocked():
    inventory = Inventory()
    inventory.add("D-1", 3)
    inventory.add("L-2", 5)
    inventory.add("S-3", 20)
    return inventory


LEVELS = ("D-1", "L-2", "S-3")


def levels(inventory):
    return [(inventory.on_hand(s), inventory.reserved(s), inventory.available(s)) for s in LEVELS]


def test_unstocked_component_leaves_stock_as_it_was():
    inventory = stocked()
    before = levels(inventory)
    kit = Kit("lamp kit", {"D-1": 1, "L-2": 2, "B-9": 1})
    with pytest.raises(UnknownSku):
        reserve_kit(inventory, kit)
    assert inventory.reservations() == []
    assert levels(inventory) == before


def test_short_component_leaves_stock_as_it_was():
    inventory = stocked()
    before = levels(inventory)
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, Kit("desk set", {"D-1": 1, "L-2": 2, "S-3": 4}), count=3)
    assert inventory.reservations() == []
    assert levels(inventory) == before


def test_a_failed_kit_does_not_block_a_later_one():
    inventory = stocked()
    with pytest.raises(UnknownSku):
        reserve_kit(inventory, Kit("lamp kit", {"D-1": 3, "B-9": 1}))
    ids = reserve_kit(inventory, Kit("desk", {"D-1": 3}))
    assert len(ids) == 1
    assert inventory.available("D-1") == 0


def test_successful_kit_still_reserves_everything():
    inventory = stocked()
    ids = reserve_kit(inventory, Kit("desk set", {"D-1": 1, "L-2": 2, "S-3": 4}), count=2)
    assert len(ids) == 3
    assert [inventory.available(s) for s in LEVELS] == [1, 1, 12]


def test_release_returns_stock_and_closes_the_reservation():
    inventory = Inventory()
    inventory.add("W-100", 10)
    reservation_id = inventory.reserve("W-100", 6)
    released = inventory.release(reservation_id)
    assert released.quantity == 6
    assert inventory.available("W-100") == 10
    assert inventory.reserved("W-100") == 0
    with pytest.raises(UnknownReservation):
        inventory.release(reservation_id)
    with pytest.raises(UnknownReservation):
        inventory.fulfil(reservation_id)
