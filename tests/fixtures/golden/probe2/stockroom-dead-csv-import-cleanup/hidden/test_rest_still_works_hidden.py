"""Hidden: the importer's README section is gone and the rest of stockroom behaves as before."""

from pathlib import Path

import pytest

from stockroom.backorders import Backorder, fill
from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory
from stockroom.kits import Kit, reserve_kit
from stockroom.models import Item
from stockroom.reorder import order_quantity


def _root() -> Path:
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        if (candidate / "src" / "stockroom").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_readme_no_longer_documents_the_importer():
    text = (_root() / "README.md").read_text(encoding="utf-8")
    # the section is gone (a one-line note that the importer was removed may stay)
    assert "Importing a stock count" not in text
    assert "count-example.csv" not in text
    assert "## Command line" in text and "## Reordering" in text


def test_inventory_and_kits():
    inventory = Inventory()
    inventory.add("D-1", 2)
    inventory.add("L-2", 3)
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, Kit("lamp set", {"D-1": 1, "L-2": 2}), count=2)
    assert inventory.reservations() == []
    assert len(reserve_kit(inventory, Kit("lamp set", {"D-1": 1, "L-2": 2}))) == 2
    assert inventory.available("L-2") == 1


def test_backorders_and_reorder():
    inventory = Inventory()
    inventory.add("G-200", 3)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("SO-2", "G-200", 1)]
    assert [b.order_id for b, _ in fill(inventory, queue)] == ["SO-1", "SO-2"]
    assert order_quantity(Item("X", "x", daily_demand=2, lead_time_days=3, pack_size=5), available=1) == 20


def test_cli_round_trip(tmp_path, capsys):
    db = str(tmp_path / "s.json")
    assert main(["--db", db, "add", "W-100", "7"]) == 0
    assert main(["--db", db, "reserve", "W-100", "2"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "show"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 7 on hand, 2 reserved, 5 available"
