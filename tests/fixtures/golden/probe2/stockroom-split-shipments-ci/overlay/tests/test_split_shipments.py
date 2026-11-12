"""Split shipments (#58): a reservation can ship in parts. See README, "Split shipments"."""

import pytest

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory, UnknownReservation


def stocked(quantity=10):
    inventory = Inventory()
    inventory.add("W-100", quantity)
    return inventory


def test_partial_fulfil_ships_part_and_keeps_the_rest_reserved():
    inventory = stocked()
    reservation_id = inventory.reserve("W-100", 6)
    shipped = inventory.fulfil(reservation_id, 2)
    assert (shipped.reservation_id, shipped.sku, shipped.quantity) == (reservation_id, "W-100", 2)
    assert inventory.on_hand("W-100") == 8
    assert inventory.reserved("W-100") == 4
    assert inventory.available("W-100") == 4
    [still_open] = inventory.reservations()
    assert (still_open.reservation_id, still_open.quantity) == (reservation_id, 4)


def test_shipping_the_rest_closes_the_reservation():
    inventory = stocked()
    reservation_id = inventory.reserve("W-100", 6)
    inventory.fulfil(reservation_id, 2)
    assert inventory.fulfil(reservation_id, 4).quantity == 4
    assert inventory.reservations() == []
    assert inventory.on_hand("W-100") == 4
    with pytest.raises(UnknownReservation):
        inventory.fulfil(reservation_id, 1)


def test_without_a_quantity_fulfil_ships_what_is_left():
    inventory = stocked()
    reservation_id = inventory.reserve("W-100", 6)
    inventory.fulfil(reservation_id, 5)
    assert inventory.fulfil(reservation_id).quantity == 1
    assert inventory.reservations() == []
    assert inventory.on_hand("W-100") == 4


def test_a_partly_shipped_reservation_keeps_its_place():
    inventory = stocked()
    inventory.add("G-200", 5)
    first = inventory.reserve("W-100", 3)
    second = inventory.reserve("G-200", 2)
    inventory.fulfil(first, 1)
    assert [(r.reservation_id, r.quantity) for r in inventory.reservations()] == [(first, 2), (second, 2)]


def test_shipping_more_than_is_reserved_changes_nothing():
    inventory = stocked()
    reservation_id = inventory.reserve("W-100", 3)
    with pytest.raises(InsufficientStock, match=reservation_id):
        inventory.fulfil(reservation_id, 4)
    assert inventory.on_hand("W-100") == 10
    assert inventory.reserved("W-100") == 3


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_quantity_must_be_a_positive_whole_number(quantity):
    inventory = stocked()
    reservation_id = inventory.reserve("W-100", 3)
    with pytest.raises(ValueError):
        inventory.fulfil(reservation_id, quantity)
    assert inventory.reserved("W-100") == 3


def test_partly_shipped_reservations_survive_a_reload(tmp_path):
    inventory = stocked()
    reservation_id = inventory.reserve("W-100", 6)
    inventory.fulfil(reservation_id, 4)
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    loaded = storage.load(path)
    assert loaded.on_hand("W-100") == 6
    assert loaded.reserved("W-100") == 2
    assert loaded.fulfil(reservation_id).quantity == 2
    assert loaded.on_hand("W-100") == 4


def test_cli_fulfil_with_a_quantity(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    main(["--db", db, "add", "W-100", "10"])
    main(["--db", db, "reserve", "W-100", "4"])
    assert main(["--db", db, "fulfil", "R1", "--quantity", "3"]) == 0
    capsys.readouterr()
    main(["--db", db, "show", "W-100"])
    assert capsys.readouterr().out.strip() == "W-100: 7 on hand, 1 reserved, 6 available"
