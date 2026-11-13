from datetime import date, timedelta

import pytest

from stockroom.lots import LotStore, PickLine, ShortPick

SHIP = date(2027, 2, 1)


def day(n):
    return SHIP + timedelta(days=n)


def ids(picks):
    return [(line.lot_id, line.quantity) for line in picks]


@pytest.mark.parametrize("min_shelf_days", [1, 2, 5])
def test_exactly_the_minimum_shelf_life_is_sellable(min_shelf_days):
    store = LotStore()
    store.receive("CHEESE-9", 4, day(min_shelf_days - 1))
    store.receive("CHEESE-9", 4, day(min_shelf_days))
    assert ids(store.pick("CHEESE-9", 4, SHIP, min_shelf_days=min_shelf_days)) == [("L2", 4)]


def test_expiring_on_or_before_the_ship_date_never_ships():
    store = LotStore()
    store.receive("CHEESE-9", 4, day(-1))
    store.receive("CHEESE-9", 4, day(0))
    store.receive("CHEESE-9", 4, day(1))
    assert ids(store.pick("CHEESE-9", 4, SHIP)) == [("L3", 4)]
    with pytest.raises(ShortPick):
        store.pick("CHEESE-9", 5, SHIP)


def test_same_expiry_keeps_receipt_order_beyond_ten_lots():
    store = LotStore()
    for _ in range(12):
        store.receive("EGGS-3", 2, day(10))
    store.receive("EGGS-3", 50, day(30))
    picked = store.pick("EGGS-3", 25, SHIP)
    assert ids(picked) == [(f"L{n}", 2) for n in range(1, 13)] + [("L13", 1)]


def test_earliest_expiry_first_regardless_of_receipt_order():
    store = LotStore()
    store.receive("EGGS-3", 5, day(20))
    store.receive("EGGS-3", 5, day(6))
    store.receive("EGGS-3", 5, day(12))
    assert ids(store.pick("EGGS-3", 12, SHIP)) == [("L2", 5), ("L3", 5), ("L1", 2)]


def test_short_pick_counts_only_sellable_lots_and_changes_nothing():
    store = LotStore()
    store.receive("EGGS-3", 20, day(1))
    store.receive("EGGS-3", 3, day(9))
    with pytest.raises(ShortPick):
        store.pick("EGGS-3", 4, SHIP, min_shelf_days=4)
    assert [(lot.lot_id, lot.quantity) for lot in store.lots("EGGS-3")] == [("L1", 20), ("L2", 3)]
    assert ids(store.pick("EGGS-3", 3, SHIP, min_shelf_days=4)) == [("L2", 3)]


def test_commit_after_pick():
    store = LotStore()
    store.receive("EGGS-3", 3, day(4))
    store.receive("EGGS-3", 6, day(8))
    store.commit(store.pick("EGGS-3", 5, SHIP))
    assert [(lot.lot_id, lot.quantity) for lot in store.lots("EGGS-3")] == [("L2", 4)]
    assert store.pick("EGGS-3", 4, SHIP) == [PickLine("L2", 4)]
