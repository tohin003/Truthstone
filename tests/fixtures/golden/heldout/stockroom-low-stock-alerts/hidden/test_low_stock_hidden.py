"""Low-stock alerts: the Inventory method, the text output, the exit status and --json."""

import json

import pytest

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import Inventory


def stocked():
    inventory = Inventory()
    inventory.add("W-100", 10)  # 7 available after the reservation below
    inventory.add("G-200", 4)  # 1 available
    inventory.add("D-1", 3)  # 3 available
    inventory.add("A-9", 20)  # 20 available
    inventory.reserve("W-100", 3)
    inventory.reserve("G-200", 3)
    return inventory


def test_low_stock_is_available_at_or_below_the_threshold_sorted_by_sku():
    inventory = stocked()
    assert inventory.low_stock(3) == ["D-1", "G-200"]
    assert inventory.low_stock(0) == []
    assert inventory.low_stock(1) == ["G-200"]
    assert inventory.low_stock(7) == ["D-1", "G-200", "W-100"]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "stock.json"
    storage.save(stocked(), path)
    return str(path)


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    return code, capsys.readouterr().out


def test_cli_lists_low_skus_and_exits_1(db, capsys):
    code, out = run(["--db", db, "low-stock", "--threshold", "3"], capsys)
    assert out.splitlines() == ["D-1: 3 available (0 reserved)", "G-200: 1 available (3 reserved)"]
    assert code == 1


def test_cli_exits_0_when_nothing_is_low(db, capsys):
    code, out = run(["--db", db, "low-stock", "--threshold", "0"], capsys)
    assert out.strip() == ""
    assert code == 0


def test_cli_json_output(db, capsys):
    code, out = run(["--db", db, "low-stock", "--threshold", "3", "--json"], capsys)
    assert json.loads(out) == [
        {"sku": "D-1", "available": 3, "reserved": 0},
        {"sku": "G-200", "available": 1, "reserved": 3},
    ]
    assert code == 1


def test_cli_json_output_when_nothing_is_low(db, capsys):
    code, out = run(["--db", db, "low-stock", "--threshold", "0", "--json"], capsys)
    assert json.loads(out) == []
    assert code == 0


def test_other_commands_are_unchanged(db, capsys):
    code, out = run(["--db", db, "show", "G-200"], capsys)
    assert code == 0
    assert out.strip() == "G-200: 4 on hand, 3 reserved, 1 available"
