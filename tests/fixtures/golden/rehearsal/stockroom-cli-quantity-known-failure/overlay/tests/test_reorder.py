from stockroom.inventory import Inventory
from stockroom.models import Item
from stockroom.reorder import order_quantity, reorder_point, suggestions

LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6)
SCREWS = Item("S-3", "Screws", daily_demand=2.5, lead_time_days=3)


def test_reorder_point_is_lead_time_demand_plus_safety_stock():
    assert reorder_point(LAMP) == 26


def test_reorder_point_rounds_demand_up():
    assert reorder_point(SCREWS) == 8
    assert reorder_point(Item("P-4", "Paper", daily_demand=1.2, lead_time_days=5)) == 6


def test_nothing_to_order_above_the_reorder_point():
    assert order_quantity(LAMP, available=27) == 0


def test_orders_up_to_the_target_at_or_below_the_reorder_point():
    # target = 26 + 4 x 7 = 54
    assert order_quantity(LAMP, available=26) == 28
    assert order_quantity(LAMP, available=10) == 44


def test_orders_whole_packs():
    boxed = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6, pack_size=12)
    assert order_quantity(boxed, available=26) == 36  # 28 units, rounded up to 3 packs


def test_suggestions_use_available_stock():
    inventory = Inventory()
    inventory.add("L-2", 30)
    inventory.add("S-3", 50)
    assert suggestions(inventory, [LAMP, SCREWS]) == {}
    inventory.reserve("L-2", 5)  # 25 available: below the reorder point
    assert suggestions(inventory, [LAMP, SCREWS]) == {"L-2": 29}


def test_orders_at_least_the_supplier_minimum():
    # Known failure: #31, see KNOWN_ISSUES.md. Don't implement it as part of other changes.
    bolts = Item("B-12", "Bolts", daily_demand=2, lead_time_days=3, pack_size=10, min_order=200)
    assert order_quantity(bolts, available=0) == 200
