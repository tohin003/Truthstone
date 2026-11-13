import pytest

from stockroom.cyclecount import apply_count, variance_report
from stockroom.inventory import InsufficientStock, Inventory


def stocked():
    inventory = Inventory()
    inventory.add("W-100", 10)
    inventory.add("G-200", 5)
    inventory.add("B-300", 8)
    return inventory


def test_count_above_on_hand_adds_the_difference():
    inventory = stocked()
    assert apply_count(inventory, "G-200", 9) == 4
    assert inventory.on_hand("G-200") == 9


def test_count_below_on_hand_keeps_reservations():
    inventory = stocked()
    inventory.reserve("W-100", 4)
    assert apply_count(inventory, "W-100", 7) == -3
    assert inventory.on_hand("W-100") == 7
    assert inventory.available("W-100") == 3


def test_count_below_reserved_is_refused():
    inventory = stocked()
    inventory.reserve("W-100", 6)
    with pytest.raises(InsufficientStock):
        apply_count(inventory, "W-100", 5)
    assert inventory.on_hand("W-100") == 10


def test_variance_report():
    inventory = stocked()
    sheet = {"W-100": 9, "G-200": 5, "B-300": 11}
    assert variance_report(inventory, sheet) == [("B-300", 8, 11, 3), ("W-100", 10, 9, -1)]
