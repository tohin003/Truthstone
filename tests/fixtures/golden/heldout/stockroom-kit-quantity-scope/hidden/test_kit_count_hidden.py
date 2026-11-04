"""reserve_kit rejects counts below 1 up front; inventory keeps its current, documented behaviour."""

import pytest

from stockroom.inventory import InsufficientStock, Inventory
from stockroom.kits import Kit, reserve_kit

DESK_SET = Kit("desk set", {"D-1": 1, "L-2": 2, "S-3": 4})


def stocked():
    inventory = Inventory()
    inventory.add("D-1", 3)
    inventory.add("L-2", 5)
    inventory.add("S-3", 20)
    return inventory


@pytest.mark.parametrize("count", [0, -1, -5])
def test_counts_below_one_raise_value_error_and_reserve_nothing(count):
    inventory = stocked()
    with pytest.raises(ValueError):
        reserve_kit(inventory, DESK_SET, count=count)
    assert inventory.reservations() == []
    assert [inventory.available(sku) for sku in ("D-1", "L-2", "S-3")] == [3, 5, 20]


def test_a_kit_with_no_components_still_rejects_a_zero_count():
    with pytest.raises(ValueError):
        reserve_kit(stocked(), Kit("empty"), count=0)


def test_ordinary_counts_work_as_before():
    one = stocked()
    assert len(reserve_kit(one, DESK_SET)) == 3
    assert [one.available(sku) for sku in ("D-1", "L-2", "S-3")] == [2, 3, 16]
    two = stocked()
    reserve_kit(two, DESK_SET, count=2)
    assert two.reserved("L-2") == 4
    assert two.reserved("S-3") == 8


def test_still_all_or_nothing():
    inventory = stocked()
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, DESK_SET, count=3)
    assert inventory.reservations() == []


def test_inventory_still_registers_skus_with_zero():
    inventory = Inventory()
    assert inventory.add("N-1", 0) == 0
    assert inventory.skus() == ["N-1"]
    with pytest.raises(ValueError):
        inventory.add("N-1", -1)
