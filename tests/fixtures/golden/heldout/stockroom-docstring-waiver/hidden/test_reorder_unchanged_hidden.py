"""order_quantity behaves exactly as before: the task changes its docstring only."""

import inspect

from stockroom.models import Item
from stockroom.reorder import REVIEW_DAYS, order_quantity, reorder_point

LAMP = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6)


def test_signature_unchanged():
    parameters = inspect.signature(order_quantity).parameters
    assert list(parameters) == ["item", "available", "review_days"]
    assert parameters["review_days"].default == REVIEW_DAYS == 7


def test_quantities_unchanged():
    assert reorder_point(LAMP) == 26
    assert order_quantity(LAMP, available=27) == 0
    assert order_quantity(LAMP, available=26) == 28
    assert order_quantity(LAMP, available=10) == 44


def test_whole_packs_are_still_rounded_up():
    boxed = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6, pack_size=12)
    assert order_quantity(boxed, available=26) == 36  # 28 units -> 3 packs, never 2
    assert order_quantity(boxed, available=10) == 48  # 44 units -> 4 packs
