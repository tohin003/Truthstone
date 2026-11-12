import math

import pytest

from stockroom.inventory import Inventory
from stockroom.models import Item
from stockroom.reorder import order_quantity, reorder_point, suggestions

LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6)
BOXED_LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6, pack_size=12)
CABLE = Item("C-9", "Cable", daily_demand=3, lead_time_days=2, safety_stock=4, pack_size=10)
TAPE = Item("T-5", "Tape", daily_demand=1.5, lead_time_days=4, safety_stock=2, pack_size=6)


def target(item, review_days=7):
    return reorder_point(item) + math.ceil(round(item.daily_demand * review_days, 9))


def test_documented_examples_are_unchanged():
    assert reorder_point(LAMP) == 26
    assert order_quantity(LAMP, available=26) == 28
    assert order_quantity(LAMP, available=10) == 44
    assert order_quantity(LAMP, available=27) == 0


def test_whole_packs_rounded_up_to_reach_the_target():
    # 54 - 26 = 28 units short: three packs of 12, not two.
    assert order_quantity(BOXED_LAMP, available=26) == 36
    # target 31, nothing available: 31 units short, four packs of 10.
    assert order_quantity(CABLE, available=0) == 40


@pytest.mark.parametrize("item", [BOXED_LAMP, CABLE, TAPE])
@pytest.mark.parametrize("available", [0, 1, 5, 9, 13])
def test_every_order_is_whole_packs_and_reaches_the_target(item, available):
    if available > reorder_point(item):
        assert order_quantity(item, available) == 0
        return
    quantity = order_quantity(item, available)
    assert quantity % item.pack_size == 0
    assert available + quantity >= target(item)
    # rounded *up*: one pack fewer would fall short of the target
    assert available + quantity - item.pack_size < target(item)


def test_suggestions_round_up_to_packs():
    inventory = Inventory()
    inventory.add("L-2", 26)
    inventory.add("C-9", 50)
    assert suggestions(inventory, [BOXED_LAMP, CABLE]) == {"L-2": 36}
