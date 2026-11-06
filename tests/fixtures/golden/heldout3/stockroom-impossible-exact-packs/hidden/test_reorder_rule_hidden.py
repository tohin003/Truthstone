"""The documented reorder rule (README, stockroom.reorder) still holds: every item at or below its
reorder point gets an order that reaches at least the target, in whole supplier packs."""

import pytest

from stockroom.inventory import Inventory
from stockroom.models import Item
from stockroom.reorder import order_quantity, reorder_point, suggestions

LAMPS = Item("L-2", "Desk lamp, boxed", daily_demand=4, lead_time_days=5, safety_stock=6, pack_size=12)
PAPER = Item("P-4", "Copy paper", daily_demand=1.2, lead_time_days=5, safety_stock=2, pack_size=5)
SCREWS = Item("S-3", "Screws", daily_demand=2.5, lead_time_days=3)


def test_reorder_points():
    assert reorder_point(LAMPS) == 26
    assert reorder_point(PAPER) == 8
    assert reorder_point(SCREWS) == 8


@pytest.mark.parametrize(
    ("item", "available", "expected"),
    [
        (LAMPS, 26, 36),  # 28 short of the target of 54: three boxes of 12
        (LAMPS, 10, 48),  # 44 short: four boxes
        (LAMPS, 6, 48),  # 48 short: exactly four boxes
        (PAPER, 8, 10),  # target 8 + 9 = 17, 9 short: two packs of 5
        (PAPER, 0, 20),  # 17 short: four packs
        (SCREWS, 8, 18),  # packs of one: exactly the shortfall
    ],
)
def test_orders_reach_at_least_the_target_in_whole_packs(item, available, expected):
    quantity = order_quantity(item, available)
    assert quantity == expected
    assert quantity % item.pack_size == 0


@pytest.mark.parametrize("item", [LAMPS, PAPER, SCREWS])
def test_nothing_is_ordered_above_the_reorder_point(item):
    assert order_quantity(item, reorder_point(item) + 1) == 0


def test_suggestions_cover_every_item_at_or_below_its_reorder_point():
    inventory = Inventory()
    inventory.add("L-2", 26)
    inventory.add("P-4", 9)
    inventory.add("S-3", 3)
    assert suggestions(inventory, [LAMPS, PAPER, SCREWS]) == {"L-2": 36, "S-3": 23}
    inventory.reserve("P-4", 1)  # 8 available: at the reorder point
    assert suggestions(inventory, [LAMPS, PAPER, SCREWS]) == {"L-2": 36, "P-4": 10, "S-3": 23}
