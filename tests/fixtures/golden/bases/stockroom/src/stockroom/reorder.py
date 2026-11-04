"""When to reorder, and how much.

For an item with average daily demand ``d``, supplier lead time ``L`` days and safety
stock ``s``:

    reorder point = ceil(d × L) + s

An item needs reordering when its *available* stock (on hand minus reserved) is at or
below its reorder point. The order then tops available stock up to

    target = reorder point + ceil(d × review_days)

rounded up to whole supplier packs, so that one order lasts until the next stock review.
"""

from __future__ import annotations

import math

from stockroom.inventory import Inventory
from stockroom.models import Item

REVIEW_DAYS = 7


def _ceil(value: float) -> int:
    """``math.ceil`` that ignores float noise: 1.2 × 5 is 6, not 6.000000000000001."""
    return math.ceil(round(value, 9))


def reorder_point(item: Item) -> int:
    """The available-stock level at or below which ``item`` should be reordered."""
    return _ceil(item.daily_demand * item.lead_time_days) + item.safety_stock


def order_quantity(item: Item, available: int, review_days: int = REVIEW_DAYS) -> int:
    """Units to order now: 0 above the reorder point, otherwise enough to reach the target."""
    point = reorder_point(item)
    if available > point:
        return 0
    target = point + _ceil(item.daily_demand * review_days)
    packs = math.ceil((target - available) / item.pack_size)
    return packs * item.pack_size


def suggestions(inventory: Inventory, items: list[Item], review_days: int = REVIEW_DAYS) -> dict[str, int]:
    """Order quantities by SKU, for every item that needs reordering."""
    result: dict[str, int] = {}
    for item in items:
        quantity = order_quantity(item, inventory.available(item.sku), review_days)
        if quantity:
            result[item.sku] = quantity
    return result
