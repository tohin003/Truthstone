from datetime import date

import pytest

from stockroom.lots import LotStore, PickLine, ShortPick

SHIP = date(2026, 11, 16)


def test_receive_numbers_lots_in_order():
    store = LotStore()
    assert store.receive("YOG-1", 10, date(2026, 11, 30)) == "L1"
    assert store.receive("YOG-1", 5, date(2026, 11, 20)) == "L2"
    assert [lot.lot_id for lot in store.lots("YOG-1")] == ["L1", "L2"]


def test_earliest_expiry_ships_first_and_lines_split_across_lots():
    store = LotStore()
    store.receive("YOG-1", 10, date(2026, 11, 30))
    store.receive("YOG-1", 4, date(2026, 11, 20))
    assert store.pick("YOG-1", 6, SHIP) == [PickLine("L2", 4), PickLine("L1", 2)]


def test_a_lot_expiring_on_the_ship_date_never_ships():
    store = LotStore()
    store.receive("YOG-1", 5, SHIP)
    store.receive("YOG-1", 5, date(2026, 11, 25))
    assert store.pick("YOG-1", 3, SHIP) == [PickLine("L2", 3)]


def test_short_pick_when_there_is_not_enough_stock():
    store = LotStore()
    store.receive("YOG-1", 3, date(2026, 11, 30))
    with pytest.raises(ShortPick):
        store.pick("YOG-1", 4, SHIP)


def test_commit_takes_the_units_out():
    store = LotStore()
    store.receive("YOG-1", 4, date(2026, 11, 20))
    store.receive("YOG-1", 10, date(2026, 11, 30))
    store.commit(store.pick("YOG-1", 6, SHIP))
    assert [(lot.lot_id, lot.quantity) for lot in store.lots("YOG-1")] == [("L2", 8)]


def test_minimum_shelf_life_boundary():
    # Policy example: with min_shelf_days=3, 3 days left is sellable, 2 days left is not.
    store = LotStore()
    store.receive("YOG-1", 5, date(2026, 11, 18))  # 2 days left
    store.receive("YOG-1", 5, date(2026, 11, 19))  # 3 days left
    store.receive("YOG-1", 5, date(2026, 11, 26))
    assert store.pick("YOG-1", 7, SHIP, min_shelf_days=3) == [PickLine("L2", 5), PickLine("L3", 2)]


def test_same_expiry_ships_in_receipt_order():
    store = LotStore()
    for _ in range(11):
        store.receive("MILK-2", 1, date(2026, 11, 22))
    picked = store.pick("MILK-2", 11, SHIP)
    assert [line.lot_id for line in picked] == [f"L{n}" for n in range(1, 12)]


def test_unsellable_lots_do_not_count_towards_a_line():
    store = LotStore()
    store.receive("YOG-1", 8, date(2026, 11, 17))  # 1 day left: too short for min_shelf_days=2
    store.receive("YOG-1", 3, date(2026, 11, 28))
    with pytest.raises(ShortPick):
        store.pick("YOG-1", 5, SHIP, min_shelf_days=2)
    assert [lot.quantity for lot in store.lots("YOG-1")] == [8, 3]
