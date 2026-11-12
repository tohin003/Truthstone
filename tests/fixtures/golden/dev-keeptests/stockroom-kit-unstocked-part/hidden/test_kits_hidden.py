import pytest

from stockroom.inventory import InsufficientStock, Inventory, UnknownSku
from stockroom.kits import Kit, reserve_kit

LAMP_KIT = Kit("lamp kit", {"B-10": 1, "C-20": 2, "H-30": 1})


def stock(**levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku.replace("_", "-"), quantity)
    return inventory


@pytest.mark.parametrize("missing", ["B-10", "C-20", "H-30"])
def test_a_never_stocked_component_anywhere_in_the_kit_reserves_nothing(missing):
    levels = {"B_10": 4, "C_20": 9, "H_30": 2}
    del levels[missing.replace("-", "_")]
    inventory = stock(**levels)
    with pytest.raises(UnknownSku):
        reserve_kit(inventory, LAMP_KIT, count=2)
    assert inventory.reservations() == []
    for sku in inventory.skus():
        assert inventory.reserved(sku) == 0


def test_a_shortfall_still_reserves_nothing():
    inventory = stock(B_10=4, C_20=3, H_30=2)
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, LAMP_KIT, count=2)  # C-20 needs 4
    assert inventory.reservations() == []
    assert inventory.available("B-10") == 4


def test_a_failed_kit_leaves_earlier_reservations_alone():
    inventory = stock(B_10=4, C_20=9, X_99=5)
    earlier = inventory.reserve("B-10", 1)
    with pytest.raises(UnknownSku):
        reserve_kit(inventory, LAMP_KIT)
    assert [r.reservation_id for r in inventory.reservations()] == [earlier]
    assert inventory.available("B-10") == 3


def test_a_kit_that_fits_still_reserves_every_component():
    inventory = stock(B_10=4, C_20=9, H_30=2)
    ids = reserve_kit(inventory, LAMP_KIT, count=2)
    assert len(ids) == 3
    assert {sku: inventory.reserved(sku) for sku in ("B-10", "C-20", "H-30")} == {"B-10": 2, "C-20": 4, "H-30": 2}


def test_a_count_below_one_is_refused_before_anything_is_reserved():
    inventory = stock(B_10=4, C_20=9, H_30=2)
    with pytest.raises(ValueError):
        reserve_kit(inventory, LAMP_KIT, count=0)
    assert inventory.reservations() == []
