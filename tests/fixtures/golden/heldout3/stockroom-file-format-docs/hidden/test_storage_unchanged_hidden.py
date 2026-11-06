"""A docs-only change: the inventory file is written and read exactly as before."""

import json

import pytest

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import Inventory


def test_the_file_layout_is_unchanged(tmp_path):
    inventory = Inventory()
    inventory.add("W-100", 10)
    inventory.add("G-200", 3)
    inventory.reserve("W-100", 4)
    inventory.release(inventory.reserve("G-200", 1))
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "format": 1,
        "next_id": 3,
        "on_hand": {"G-200": 3, "W-100": 10},
        "reservations": [{"quantity": 4, "reservation_id": "R1", "sku": "W-100"}],
    }
    assert path.read_text(encoding="utf-8").endswith("}\n")


def test_reading_it_back(tmp_path):
    path = tmp_path / "stock.json"
    path.write_text(
        json.dumps(
            {
                "format": 1,
                "next_id": 8,
                "on_hand": {"W-100": 10},
                "reservations": [{"quantity": 4, "reservation_id": "R5", "sku": "W-100"}],
            }
        ),
        encoding="utf-8",
    )
    loaded = storage.load(path)
    assert loaded.available("W-100") == 6
    assert loaded.reserve("W-100", 1) == "R8"


def test_other_formats_are_still_refused(tmp_path):
    path = tmp_path / "stock.json"
    path.write_text(json.dumps({"format": 2, "on_hand": {}}), encoding="utf-8")
    with pytest.raises(storage.StorageError):
        storage.load(path)


def test_the_cli_still_works(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "5"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "show"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 5 on hand, 0 reserved, 5 available"
