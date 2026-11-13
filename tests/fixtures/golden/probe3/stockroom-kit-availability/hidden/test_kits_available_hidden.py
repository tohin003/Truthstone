import pytest

from stockroom.inventory import InsufficientStock, Inventory
from stockroom.kits import Kit, kits_available, reserve_kit

DESK_SET = Kit("desk set", {"D-1": 1, "L-2": 2, "S-3": 4})


def stocked():
    inventory = Inventory()
    inventory.add("D-1", 3)
    inventory.add("L-2", 5)
    inventory.add("S-3", 20)
    return inventory


def test_the_scarcest_component_decides():
    # D-1: 3 kits, L-2: 5 // 2 = 2 kits, S-3: 20 // 4 = 5 kits
    assert kits_available(stocked(), DESK_SET) == 2


def test_reserved_stock_does_not_count():
    inventory = stocked()
    inventory.reserve("L-2", 2)  # 3 available: one kit's worth
    assert kits_available(inventory, DESK_SET) == 1
    inventory.reserve("D-1", 3)
    assert kits_available(inventory, DESK_SET) == 0


def test_a_never_stocked_component_means_no_kits():
    kit = Kit("lamp kit", {"L-2": 1, "B-9": 1})
    assert kits_available(stocked(), kit) == 0


def test_a_kit_without_components_is_an_error():
    with pytest.raises(ValueError):
        kits_available(stocked(), Kit("empty"))


def test_the_answer_is_what_reserve_kit_can_do():
    inventory = stocked()
    inventory.add("L-2", 4)  # 9 L-2: 4 kits by L-2, 3 by D-1
    count = kits_available(inventory, DESK_SET)
    assert count == 3
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, DESK_SET, count=count + 1)
    assert len(reserve_kit(inventory, DESK_SET, count=count)) == 3
    assert kits_available(inventory, DESK_SET) == 0


def test_checking_reserves_nothing():
    inventory = stocked()
    kits_available(inventory, DESK_SET)
    assert inventory.reservations() == []
    assert [inventory.available(sku) for sku in ("D-1", "L-2", "S-3")] == [3, 5, 20]
