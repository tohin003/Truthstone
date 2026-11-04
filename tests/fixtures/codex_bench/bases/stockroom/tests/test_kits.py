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


def test_reserves_every_component():
    inventory = stocked()
    ids = reserve_kit(inventory, DESK_SET)
    assert len(ids) == 3
    assert [inventory.available(sku) for sku in ("D-1", "L-2", "S-3")] == [2, 3, 16]


def test_count_multiplies_components():
    inventory = stocked()
    reserve_kit(inventory, DESK_SET, count=2)
    assert inventory.reserved("L-2") == 4
    assert inventory.reserved("S-3") == 8


def test_all_or_nothing():
    inventory = stocked()
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, DESK_SET, count=3)  # L-2 needs 6 and only 5 are on hand
    assert inventory.reservations() == []
    assert inventory.available("D-1") == 3
