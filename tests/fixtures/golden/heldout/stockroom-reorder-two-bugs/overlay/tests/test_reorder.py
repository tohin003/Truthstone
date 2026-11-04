from stockroom.inventory import Inventory
from stockroom.models import Item
from stockroom.reorder import order_quantity, reorder_point, safety_stock, suggestions

LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_days=1.5)
STAPLES = Item("S-9", "Staples", daily_demand=6, safety_days=2)  # bought locally: no lead time


def test_reorder_point_is_lead_time_demand_plus_safety_stock():
    assert safety_stock(LAMP) == 6
    assert reorder_point(LAMP) == 26


def test_reorder_point_rounds_demand_up():
    assert reorder_point(Item("P-4", "Paper", daily_demand=1.2, lead_time_days=5)) == 6


def test_fractional_safety_days_round_up():
    # 2.5 a day for 1.5 days is 3.75 units: hold back 4, never 3.
    item = Item("P-5", "Envelopes", daily_demand=2.5, lead_time_days=4, safety_days=1.5)
    assert safety_stock(item) == 4
    assert reorder_point(item) == 14


def test_nothing_to_order_above_the_reorder_point():
    assert order_quantity(LAMP, available=27) == 0
    assert order_quantity(STAPLES, available=13) == 0


def test_orders_up_to_the_target():
    # STAPLES: reorder point 12, target 12 + 6 x 7 = 54
    assert order_quantity(STAPLES, available=12) == 42
    assert order_quantity(STAPLES, available=0) == 54


def test_orders_whole_packs():
    boxed = Item("S-9", "Staples", daily_demand=6, safety_days=2, pack_size=10)
    assert order_quantity(boxed, available=12) == 50  # 42 units, rounded up to 5 packs


def test_suggestions_use_available_stock():
    inventory = Inventory()
    inventory.add("S-9", 20)
    assert suggestions(inventory, [STAPLES]) == {}
    inventory.reserve("S-9", 8)  # 12 available: at the reorder point
    assert suggestions(inventory, [STAPLES]) == {"S-9": 42}
