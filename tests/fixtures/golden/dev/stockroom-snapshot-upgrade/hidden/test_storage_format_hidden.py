"""Storage stays on format 2: new files are format 2, read back intact, and unknown formats fail."""

import json

import pytest

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


def test_saves_format_2_and_reads_it_back(tmp_path):
    path = tmp_path / "stock.json"
    storage.save(stocked(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert storage.FORMAT_VERSION == 2
    assert data["format"] == 2
    assert data["items"] == {"G-200": {"on_hand": 3}, "W-100": {"on_hand": 10}}
    loaded = storage.load(path)
    assert loaded.skus() == ["G-200", "W-100"]
    assert loaded.available("W-100") == 6
    assert [r.reservation_id for r in loaded.reservations()] == ["R1"]
    assert loaded.reserve("G-200", 1) == "R3"


@pytest.mark.parametrize("payload", [{"format": 99}, {"format": 3, "items": {}}, ["not", "an", "inventory"]])
def test_unknown_formats_are_rejected(tmp_path, payload):
    path = tmp_path / "stock.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(storage.StorageError):
        storage.load(path)


def test_the_cli_writes_format_2(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "5"]) == 0
    assert main(["--db", db, "reserve", "W-100", "2"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "show"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 5 on hand, 2 reserved, 3 available"
    assert json.loads((tmp_path / "stock.json").read_text(encoding="utf-8"))["format"] == 2
