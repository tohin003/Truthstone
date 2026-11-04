"""Inventory.fulfil() is now Inventory.ship(), and `stockroom fulfil` is now `stockroom ship`."""

import re
from pathlib import Path

import pytest

from stockroom.backorders import Backorder, fill, ship_ready
from stockroom.cli import main
from stockroom.inventory import Inventory, UnknownReservation


def stocked(levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku, quantity)
    return inventory


def test_ship_ships_reserved_stock():
    inventory = stocked({"W-100": 10})
    reservation_id = inventory.reserve("W-100", 4)
    shipped = inventory.ship(reservation_id)
    assert shipped.quantity == 4
    assert inventory.on_hand("W-100") == 6
    assert inventory.available("W-100") == 6
    with pytest.raises(UnknownReservation):
        inventory.ship(reservation_id)


def test_the_old_method_is_gone():
    assert not hasattr(Inventory, "fulfil")
    assert not hasattr(Inventory(), "fulfil")


def test_backorders_ship_through_the_new_name():
    inventory = Inventory()
    inventory.add("G-200", 3)
    filled = fill(inventory, [Backorder("SO-1", "G-200", 2)])
    assert ship_ready(inventory, filled) == ["SO-1"]
    assert inventory.on_hand("G-200") == 1
    assert inventory.reservations() == []


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "stock.json")
    assert main(["--db", path, "add", "W-100", "10"]) == 0
    assert main(["--db", path, "reserve", "W-100", "4"]) == 0
    return path


def show(db, capsys):
    capsys.readouterr()
    assert main(["--db", db, "show", "W-100"]) == 0
    return capsys.readouterr().out.strip()


def test_cli_ship_command(db, capsys):
    assert main(["--db", db, "ship", "R1"]) == 0
    assert show(db, capsys) == "W-100: 6 on hand, 0 reserved, 6 available"


def test_cli_ship_reports_an_unknown_reservation(db, capsys):
    capsys.readouterr()
    assert main(["--db", db, "ship", "R9"]) == 1
    assert "R9" in capsys.readouterr().err


def test_cli_fulfil_command_is_gone(db, capsys):
    try:
        code = main(["--db", db, "fulfil", "R1"])
    except SystemExit as exc:
        code = exc.code
    assert code not in (0, None)
    assert show(db, capsys) == "W-100: 10 on hand, 4 reserved, 6 available"


def test_cli_release_still_works(db, capsys):
    assert main(["--db", db, "release", "R1"]) == 0
    assert show(db, capsys) == "W-100: 10 on hand, 0 reserved, 10 available"


def test_readme_uses_the_new_names():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "stockroom ship" in readme
    assert "ship(" in readme
    assert not re.search(r"stockroom fulfil\b", readme)
    assert not re.search(r"\bfulfil\(", readme)
