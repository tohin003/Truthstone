"""Three years of daily demand for the whole catalogue, replayed against the reorder policy.

This is the regression test for the reorder policy as a whole, and it is slow on purpose (well
over a minute): every day, every catalogue item sells, gets its reorder check, and receives the
orders placed a lead time ago. Demand comes from a fixed pseudo-random sequence, so every run
replays the same three years.
"""

from stockroom.inventory import Inventory
from stockroom.models import Item
from stockroom.reorder import order_quantity, reorder_point

DAYS = 3 * 365
CATALOGUE_SIZE = 18000


def sequence(seed):
    """A deterministic pseudo-random sequence (a linear congruential generator), 0 <= n < 2**31."""
    state = seed
    while True:
        state = (1103515245 * state + 12345) % 2**31
        yield state


def catalogue():
    numbers = sequence(7)
    items = []
    for n in range(CATALOGUE_SIZE):
        items.append(
            Item(
                f"S-{n:04d}",
                f"catalogue item {n}",
                daily_demand=0.5 + (next(numbers) % 400) / 100,
                lead_time_days=2 + next(numbers) % 12,
                safety_stock=4 + next(numbers) % 10,
                pack_size=(1, 6, 12)[next(numbers) % 3],
            )
        )
    return items


def test_three_years_of_demand_stay_in_stock():
    items = catalogue()
    inventory = Inventory()
    for item in items:
        inventory.add(item.sku, reorder_point(item) + 10)
    numbers = sequence(11)
    arriving: dict[int, list[tuple[str, int]]] = {}
    on_order = {item.sku: 0 for item in items}
    sales_days = short_days = 0
    for day in range(DAYS):
        for sku, quantity in arriving.pop(day, []):
            inventory.add(sku, quantity)
            on_order[sku] -= quantity
        for item in items:
            wanted = int(item.daily_demand * 2 * (next(numbers) % 1000) / 1000 + 0.5)
            if wanted:
                sales_days += 1
                available = inventory.available(item.sku)
                if wanted > available:
                    short_days += 1
                    wanted = available
                if wanted:
                    inventory.remove(item.sku, wanted)
            quantity = order_quantity(item, inventory.available(item.sku) + on_order[item.sku])
            if quantity:
                arriving.setdefault(day + item.lead_time_days, []).append((item.sku, quantity))
                on_order[item.sku] += quantity
    assert sales_days > 0
    assert short_days / sales_days < 0.02
