import pytest

from stockroom.inventory import Inventory, UnknownSku
from stockroom.models import Item
from stockroom.reorder import order_quantity, suggestions

LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6)
NOTEBOOKS = Item("N-7", "Notebook", daily_demand=2, lead_time_days=3, safety_stock=4, pack_size=5)
PENS = Item("P-9", "Pens", daily_demand=1.2, lead_time_days=5, pack_size=12)


def test_never_stocked_items_are_ordered_as_if_nothing_were_available():
    inventory = Inventory()
    inventory.add("L-2", 30)
    assert suggestions(inventory, [LAMP, NOTEBOOKS, PENS]) == {
        "N-7": order_quantity(NOTEBOOKS, available=0),
        "P-9": order_quantity(PENS, available=0),
    }
    assert suggestions(inventory, [NOTEBOOKS]) == {"N-7": 25}


def test_stocked_items_are_unchanged():
    inventory = Inventory()
    inventory.add("L-2", 30)
    inventory.reserve("L-2", 5)
    assert suggestions(inventory, [LAMP]) == {"L-2": 29}


def test_unknown_skus_still_raise_in_the_inventory():
    inventory = Inventory()
    with pytest.raises(UnknownSku):
        inventory.on_hand("N-7")
    with pytest.raises(UnknownSku):
        inventory.reserve("N-7", 1)
