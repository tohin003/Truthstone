"""Never-stocked catalogue items get a full first order; the inventory still refuses unknown SKUs."""

import pytest

from stockroom.inventory import InsufficientStock, Inventory, UnknownSku
from stockroom.kits import Kit, reserve_kit
from stockroom.models import Item
from stockroom.reorder import suggestions

LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6)
DESK = Item("D-9", "Standing desk", daily_demand=1.5, lead_time_days=10, safety_stock=4, pack_size=2)
CHAIR = Item("C-3", "Chair", daily_demand=2, lead_time_days=3, safety_stock=2, pack_size=5)


def test_never_stocked_items_get_a_full_first_order():
    inventory = Inventory()
    inventory.add("L-2", 30)
    assert suggestions(inventory, [LAMP, DESK, CHAIR]) == {"D-9": 30, "C-3": 25}


def test_suggestions_do_not_add_unknown_skus_to_the_inventory():
    inventory = Inventory()
    inventory.add("L-2", 10)
    assert suggestions(inventory, [LAMP, DESK]) == {"L-2": 44, "D-9": 30}
    assert inventory.skus() == ["L-2"]


def test_stocked_items_are_unchanged():
    inventory = Inventory()
    inventory.add("L-2", 30)
    inventory.reserve("L-2", 5)
    assert suggestions(inventory, [LAMP]) == {"L-2": 29}


def test_the_inventory_still_refuses_unknown_skus():
    inventory = Inventory()
    inventory.add("W-100", 3)
    for call in (
        lambda: inventory.on_hand("NOPE"),
        lambda: inventory.reserved("NOPE"),
        lambda: inventory.available("NOPE"),
        lambda: inventory.reserve("NOPE", 1),
        lambda: inventory.remove("NOPE", 1),
    ):
        with pytest.raises(UnknownSku):
            call()
    with pytest.raises(InsufficientStock):
        inventory.reserve("W-100", 4)


def test_a_kit_with_an_unknown_component_names_it():
    inventory = Inventory()
    inventory.add("D-1", 3)
    with pytest.raises(UnknownSku):
        reserve_kit(inventory, Kit("desk set", {"D-1": 1, "NOPE": 1}))
    assert inventory.reservations() == []
