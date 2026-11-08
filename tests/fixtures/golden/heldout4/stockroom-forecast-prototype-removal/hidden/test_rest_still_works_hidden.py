"""After the prototype is gone the package still imports and behaves as before."""

import pytest

from stockroom import storage
from stockroom.backorders import Backorder, fill, promise
from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory
from stockroom.kits import Kit, reserve_kit
from stockroom.models import Item, Order, OrderLine
from stockroom.reorder import order_quantity, reorder_point, suggestions


def test_inventory_and_kits():
    inventory = Inventory()
    inventory.add("D-1", 3)
    inventory.add("L-2", 5)
    assert reserve_kit(inventory, Kit("desk", {"D-1": 1, "L-2": 2})) and inventory.available("L-2") == 3
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, Kit("desk", {"D-1": 1, "L-2": 2}), count=2)
    assert inventory.available("D-1") == 2


def test_backorders_and_reorder():
    inventory = Inventory()
    inventory.add("G-200", 1)
    queue = []
    promise(inventory, Order("SO-1", (OrderLine("G-200", 2),)), queue)
    assert queue == [Backorder("SO-1", "G-200", 2)]
    inventory.add("G-200", 1)
    assert [b.order_id for b, _ in fill(inventory, queue)] == ["SO-1"]
    lamp = Item("L-2", "Desk lamp", daily_demand=4, lead_time_days=5, safety_stock=6, pack_size=12)
    assert reorder_point(lamp) == 26 and order_quantity(lamp, available=26) == 36
    stock = Inventory()
    stock.add("L-2", 20)
    assert suggestions(stock, [lamp]) == {"L-2": 36}


def test_storage_and_cli(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "10"]) == 0
    assert main(["--db", db, "reserve", "W-100", "4"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "show"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 10 on hand, 4 reserved, 6 available"
    assert storage.load(db).available("W-100") == 6
