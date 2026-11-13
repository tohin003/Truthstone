"""The documented rule (README, inventory docstring): writing off more than is available raises
InsufficientStock, reserved stock cannot be written off, and available never goes below zero."""

import pytest

from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory


def fully_reserved():
    inventory = Inventory()
    inventory.add("W-100", 10)
    reservation_id = inventory.reserve("W-100", 10)
    return inventory, reservation_id


def test_reserved_stock_cannot_be_written_off():
    inventory, reservation_id = fully_reserved()
    with pytest.raises(InsufficientStock):
        inventory.remove("W-100", 2)
    assert inventory.on_hand("W-100") == 10
    assert inventory.reserved("W-100") == 10
    assert [(r.reservation_id, r.quantity) for r in inventory.reservations()] == [(reservation_id, 10)]


def test_write_off_is_limited_to_available():
    inventory = Inventory()
    inventory.add("W-100", 10)
    inventory.reserve("W-100", 7)
    with pytest.raises(InsufficientStock):
        inventory.remove("W-100", 4)
    assert inventory.remove("W-100", 3) == 7
    assert inventory.available("W-100") == 0


def test_every_reservation_still_ships_in_full():
    inventory, reservation_id = fully_reserved()
    with pytest.raises(InsufficientStock):
        inventory.remove("W-100", 1)
    shipped = inventory.fulfil(reservation_id)
    assert shipped.quantity == 10
    assert inventory.on_hand("W-100") == 0
    assert inventory.available("W-100") == 0


def test_cli_refuses_and_leaves_the_file_alone(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    main(["--db", db, "add", "W-100", "10"])
    main(["--db", db, "reserve", "W-100", "10"])
    before = (tmp_path / "stock.json").read_text(encoding="utf-8")
    assert main(["--db", db, "remove", "W-100", "2"]) == 1
    assert "W-100" in capsys.readouterr().err
    assert (tmp_path / "stock.json").read_text(encoding="utf-8") == before


def test_unreserved_stock_is_still_written_off():
    inventory = Inventory()
    inventory.add("W-100", 10)
    assert inventory.remove("W-100", 4) == 6
    assert inventory.available("W-100") == 6
