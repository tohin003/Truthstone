import pytest

from stockroom.cyclecount import apply_count, variance_report
from stockroom.inventory import InsufficientStock, Inventory


def stocked(**levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku.replace("_", "-"), quantity)
    return inventory


def test_a_lower_count_sets_on_hand_and_keeps_reservations():
    inventory = stocked(W_100=10)
    kept = inventory.reserve("W-100", 4)
    assert apply_count(inventory, "W-100", 7) == -3
    assert (inventory.on_hand("W-100"), inventory.reserved("W-100"), inventory.available("W-100")) == (7, 4, 3)
    assert [r.reservation_id for r in inventory.reservations("W-100")] == [kept]


def test_a_count_equal_to_the_reserved_units_leaves_nothing_available():
    inventory = stocked(W_100=10)
    inventory.reserve("W-100", 4)
    assert apply_count(inventory, "W-100", 4) == -6
    assert (inventory.on_hand("W-100"), inventory.available("W-100")) == (4, 0)


def test_a_higher_count_with_reservations():
    inventory = stocked(G_200=5)
    inventory.reserve("G-200", 2)
    assert apply_count(inventory, "G-200", 12) == 7
    assert (inventory.on_hand("G-200"), inventory.available("G-200")) == (12, 10)


def test_a_matching_count_changes_nothing():
    inventory = stocked(G_200=5)
    inventory.reserve("G-200", 1)
    assert apply_count(inventory, "G-200", 5) == 0
    assert (inventory.on_hand("G-200"), inventory.available("G-200")) == (5, 4)


def test_counting_zero_empties_an_unreserved_shelf():
    inventory = stocked(B_300=8)
    assert apply_count(inventory, "B-300", 0) == -8
    assert inventory.on_hand("B-300") == 0


def test_refusals_change_nothing():
    inventory = stocked(W_100=10)
    inventory.reserve("W-100", 6)
    with pytest.raises(InsufficientStock):
        apply_count(inventory, "W-100", 5)
    with pytest.raises(ValueError):
        apply_count(inventory, "W-100", -1)
    assert (inventory.on_hand("W-100"), inventory.reserved("W-100")) == (10, 6)


def test_variance_report_is_sorted_by_sku():
    levels = {"A-1": 3, "B-2": 4, "C-3": 5, "D-4": 6, "E-5": 7, "F-6": 8, "G-7": 9, "H-8": 10}
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku, quantity)
    sheet = {"H-8": 12, "C-3": 1, "F-6": 8, "A-1": 4, "G-7": 0, "E-5": 7, "B-2": 9, "D-4": 2}
    assert variance_report(inventory, sheet) == [
        ("A-1", 3, 4, 1),
        ("B-2", 4, 9, 5),
        ("C-3", 5, 1, -4),
        ("D-4", 6, 2, -4),
        ("G-7", 9, 0, -9),
        ("H-8", 10, 12, 2),
    ]


def test_variance_report_of_a_clean_count_is_empty():
    inventory = stocked(W_100=10, G_200=5)
    assert variance_report(inventory, {"W-100": 10, "G-200": 5}) == []
