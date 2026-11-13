import json
from pathlib import Path

import pytest

from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory


def stocked(on_hand=10, reserved=8):
    inventory = Inventory()
    inventory.add("W-100", on_hand)
    rid = inventory.reserve("W-100", reserved)
    return inventory, rid


def test_writing_off_more_than_available_raises_and_changes_nothing():
    inventory, rid = stocked()
    with pytest.raises(InsufficientStock):
        inventory.remove("W-100", 4)
    assert inventory.on_hand("W-100") == 10
    assert inventory.reserved("W-100") == 8
    assert [(r.reservation_id, r.quantity) for r in inventory.reservations("W-100")] == [(rid, 8)]


def test_available_stock_can_still_be_written_off():
    inventory, _ = stocked()
    assert inventory.remove("W-100", 2) == 8
    assert inventory.available("W-100") == 0


def test_reserved_stock_can_be_written_off_once_released():
    inventory, rid = stocked()
    inventory.release(rid)
    assert inventory.remove("W-100", 4) == 6
    assert inventory.available("W-100") == 6


def test_cli_write_off_of_reserved_stock_fails_and_leaves_the_file_alone(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    main(["--db", db, "add", "W-100", "10"])
    main(["--db", db, "reserve", "W-100", "8"])
    before = Path(db).read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(["--db", db, "remove", "W-100", "4"]) == 1
    assert "W-100" in capsys.readouterr().err
    assert Path(db).read_text(encoding="utf-8") == before
    data = json.loads(before)
    assert data["on_hand"] == {"W-100": 10}
