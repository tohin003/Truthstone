"""Saving and loading still work as documented: format 1, through a temporary file, nothing left behind."""

import json

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import Inventory


def stocked():
    inventory = Inventory()
    inventory.add("W-100", 10)
    inventory.add("G-200", 3)
    inventory.reserve("W-100", 4)
    inventory.release(inventory.reserve("G-200", 1))
    return inventory


def test_round_trip_in_format_1(tmp_path):
    path = tmp_path / "stock.json"
    storage.save(stocked(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == 1
    assert data["on_hand"] == {"G-200": 3, "W-100": 10}
    loaded = storage.load(path)
    assert loaded.available("W-100") == 6
    assert [r.reservation_id for r in loaded.reservations()] == ["R1"]
    assert loaded.reserve("G-200", 1) == "R3"


def test_a_save_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "stock.json"
    storage.save(stocked(), path)
    storage.save(stocked(), path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stock.json"]


def test_the_cli_books_and_shows_stock(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "5"]) == 0
    assert main(["--db", db, "reserve", "W-100", "2"]) == 0
    assert main(["--db", db, "fulfil", "R1"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "show"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 3 on hand, 0 reserved, 3 available"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stock.json"]
