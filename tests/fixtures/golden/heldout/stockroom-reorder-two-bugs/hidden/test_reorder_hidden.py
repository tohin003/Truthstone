"""Reorder suggestions follow the README: safety stock rounds up, the target covers the lead time."""

from stockroom.inventory import Inventory
from stockroom.models import Item
from stockroom.reorder import order_quantity, reorder_point, safety_stock, suggestions

PALLET_WRAP = Item("P-7", "Pallet wrap", daily_demand=3.5, lead_time_days=21, safety_days=2.5)
LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_days=1.5)


def test_the_reported_example():
    assert order_quantity(PALLET_WRAP, available=40) == 68


def test_safety_stock_rounds_up():
    assert safety_stock(PALLET_WRAP) == 9  # 8.75 units
    assert safety_stock(Item("P-5", "Envelopes", daily_demand=2.5, safety_days=1.5)) == 4  # 3.75
    assert safety_stock(LAMP) == 6  # exactly 6
    assert safety_stock(Item("Z-1", "Zero", daily_demand=3)) == 0


def test_reorder_points():
    assert reorder_point(PALLET_WRAP) == 83
    assert reorder_point(LAMP) == 26


def test_the_target_covers_lead_time_demand_and_the_review_period():
    # LAMP: reorder point 26, target 26 + 4 x 7 = 54
    assert order_quantity(LAMP, available=26) == 28
    assert order_quantity(LAMP, available=10) == 44
    assert order_quantity(LAMP, available=0) == 54


def test_nothing_to_order_above_the_reorder_point():
    assert order_quantity(PALLET_WRAP, available=84) == 0
    assert order_quantity(PALLET_WRAP, available=83) == 25


def test_whole_packs():
    boxed = Item("P-7", "Pallet wrap", daily_demand=3.5, lead_time_days=21, safety_days=2.5, pack_size=12)
    assert order_quantity(boxed, available=40) == 72  # 68 units, rounded up to 6 packs


def test_suggestions_use_available_stock():
    inventory = Inventory()
    inventory.add("P-7", 90)
    inventory.add("L-2", 40)
    assert suggestions(inventory, [PALLET_WRAP, LAMP]) == {}
    inventory.reserve("P-7", 50)  # 40 available
    inventory.reserve("L-2", 30)  # 10 available
    assert suggestions(inventory, [PALLET_WRAP, LAMP]) == {"P-7": 68, "L-2": 44}
