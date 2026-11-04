"""remove() refuses to take stock below zero, and a refused removal changes nothing."""

import pytest

from stockroom.inventory import InsufficientStock, Inventory, UnknownSku


def stocked(quantity):
    inventory = Inventory()
    inventory.add("W-100", quantity)
    return inventory


def test_removing_more_than_on_hand_raises_and_changes_nothing():
    inventory = stocked(5)
    with pytest.raises(InsufficientStock):
        inventory.remove("W-100", 6)
    assert inventory.on_hand("W-100") == 5
    assert inventory.available("W-100") == 5


def test_everything_can_be_removed_but_not_more():
    inventory = stocked(5)
    assert inventory.remove("W-100", 5) == 0
    with pytest.raises(InsufficientStock):
        inventory.remove("W-100", 1)
    assert inventory.on_hand("W-100") == 0


def test_ordinary_removals_still_work():
    inventory = stocked(9)
    assert inventory.remove("W-100", 2) == 7
    assert inventory.remove("W-100", 3) == 4
    assert inventory.on_hand("W-100") == 4


def test_unknown_skus_still_raise():
    with pytest.raises(UnknownSku):
        Inventory().remove("NOPE", 1)
