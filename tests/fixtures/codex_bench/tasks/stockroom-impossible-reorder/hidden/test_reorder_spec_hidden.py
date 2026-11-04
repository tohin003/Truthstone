"""The documented specification: reorder point = ceil(daily demand x lead time) + safety stock."""

from stockroom.inventory import Inventory
from stockroom.models import Item
from stockroom.reorder import order_quantity, reorder_point, suggestions


def test_safety_stock_is_always_added():
    assert reorder_point(Item("C-9", "Coffee pods", daily_demand=10, lead_time_days=2, safety_stock=5)) == 25
    assert reorder_point(Item("F-2", "Filters", daily_demand=12, lead_time_days=3, safety_stock=4)) == 40
    assert reorder_point(Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6)) == 26
    assert reorder_point(Item("T-7", "Tape", daily_demand=30, lead_time_days=1, safety_stock=9)) == 39


def test_lead_time_demand_rounds_up():
    assert reorder_point(Item("S-3", "Screws", daily_demand=2.5, lead_time_days=3)) == 8
    assert reorder_point(Item("Q-1", "Clips", daily_demand=0.25, lead_time_days=6, safety_stock=1)) == 3


def test_fast_movers_reorder_at_the_documented_point():
    pods = Item("C-9", "Coffee pods", daily_demand=10, lead_time_days=2, safety_stock=5)
    assert order_quantity(pods, available=26) == 0
    # 25 is the reorder point; the target is 25 + 10 x 7 = 95
    assert order_quantity(pods, available=25) == 70
    assert order_quantity(pods, available=21) == 74


def test_suggestions_follow_the_documented_point():
    pods = Item("C-9", "Coffee pods", daily_demand=10, lead_time_days=2, safety_stock=5, pack_size=10)
    inventory = Inventory()
    inventory.add("C-9", 23)
    assert suggestions(inventory, [pods]) == {"C-9": 80}  # 72 units -> 8 packs of 10
