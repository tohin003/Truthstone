"""Reservations never exceed what is available, whichever path tries to make them."""

import pytest

from stockroom.inventory import InsufficientStock, Inventory, UnknownReservation


def stocked(quantity=10):
    inventory = Inventory()
    inventory.add("W-100", quantity)
    return inventory


def test_the_reported_case_is_refused():
    inventory = stocked(10)
    inventory.reserve("W-100", 6)
    with pytest.raises(InsufficientStock):
        inventory.reserve("W-100", 6)
    assert inventory.reserved("W-100") == 6
    assert inventory.available("W-100") == 4


def test_exactly_what_is_available_can_be_reserved():
    inventory = stocked(10)
    inventory.reserve("W-100", 6)
    inventory.reserve("W-100", 4)
    assert inventory.available("W-100") == 0
    with pytest.raises(InsufficientStock):
        inventory.reserve("W-100", 1)


def test_a_released_reservation_cannot_be_released_again():
    inventory = stocked(10)
    reservation_id = inventory.reserve("W-100", 6)
    inventory.release(reservation_id)
    with pytest.raises(UnknownReservation):
        inventory.release(reservation_id)
    assert inventory.available("W-100") == 10
    assert inventory.reservations() == []


def test_a_double_release_cannot_free_phantom_stock():
    inventory = stocked(10)
    first = inventory.reserve("W-100", 6)
    inventory.reserve("W-100", 4)
    inventory.release(first)
    with pytest.raises(UnknownReservation):
        inventory.release(first)
    assert inventory.available("W-100") == 6
    with pytest.raises(InsufficientStock):
        inventory.reserve("W-100", 7)


def test_a_fulfilled_reservation_cannot_be_released():
    inventory = stocked(10)
    reservation_id = inventory.reserve("W-100", 3)
    inventory.fulfil(reservation_id)
    with pytest.raises(UnknownReservation):
        inventory.release(reservation_id)
    assert inventory.on_hand("W-100") == 7
    assert inventory.available("W-100") == 7


def test_reserved_matches_the_open_reservations():
    inventory = stocked(20)
    ids = [inventory.reserve("W-100", quantity) for quantity in (2, 3, 4)]
    inventory.release(ids[1])
    assert inventory.reserved("W-100") == 6
    assert sorted(r.quantity for r in inventory.reservations("W-100")) == [2, 4]
