"""A quantity below one fails like any other CLI error: message, status 1, file untouched."""

from pathlib import Path

import pytest

from stockroom.cli import main
from stockroom.inventory import Inventory


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "stock.json")
    assert main(["--db", path, "add", "W-100", "10"]) == 0
    return path


@pytest.mark.parametrize(
    ("command", "quantity"),
    [("add", "0"), ("add", "-3"), ("remove", "0"), ("reserve", "-1")],
)
def test_a_quantity_below_one_is_reported_and_exits_1(db, capsys, command, quantity):
    before = Path(db).read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(["--db", db, command, "W-100", quantity]) == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == f"stockroom: quantity must be a positive whole number, got {quantity}"
    assert captured.out == ""
    assert Path(db).read_text(encoding="utf-8") == before


def test_good_quantities_still_work(db, capsys):
    capsys.readouterr()
    assert main(["--db", db, "reserve", "W-100", "4"]) == 0
    assert main(["--db", db, "remove", "W-100", "2"]) == 0
    assert capsys.readouterr().out.splitlines() == ["R1", "8"]
    assert main(["--db", db, "show", "W-100"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 8 on hand, 4 reserved, 4 available"


def test_other_errors_are_reported_as_before(db, capsys):
    capsys.readouterr()
    assert main(["--db", db, "reserve", "W-100", "11"]) == 1
    assert "W-100" in capsys.readouterr().err


def test_the_inventory_still_rejects_bad_quantities():
    inventory = Inventory()
    with pytest.raises(ValueError):
        inventory.add("W-100", 0)
