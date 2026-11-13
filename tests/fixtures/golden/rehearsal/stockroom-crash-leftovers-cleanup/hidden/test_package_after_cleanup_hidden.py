"""After the cleanup the rest of the package imports and behaves as before."""

import pytest

from stockroom import storage
from stockroom.backorders import Backorder, fill, promise
from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory
from stockroom.kits import Kit, reserve_kit
from stockroom.models import Item, Order, OrderLine
from stockroom.reorder import order_quantity, reorder_point


def test_stock_and_reservations():
    inventory = Inventory()
    inventory.add("A-31", 12)
    reservation = inventory.reserve("A-31", 5)
    assert inventory.available("A-31") == 7
    with pytest.raises(InsufficientStock):
        inventory.remove("A-31", 8)
    inventory.fulfil(reservation)
    assert inventory.on_hand("A-31") == 7


def test_kits_backorders_and_reorder():
    inventory = Inventory()
    inventory.add("D-1", 2)
    inventory.add("H-20", 1)
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, Kit("desk", {"D-1": 1, "H-20": 2}))
    assert inventory.reservations() == []
    queue = []
    promise(inventory, Order("SO-9", (OrderLine("H-20", 3),)), queue)
    assert queue == [Backorder("SO-9", "H-20", 3)]
    inventory.add("H-20", 2)
    assert [b.order_id for b, _ in fill(inventory, queue)] == ["SO-9"]
    item = Item("K-9", "Key", daily_demand=3, lead_time_days=4, safety_stock=2, pack_size=5)
    assert reorder_point(item) == 14
    assert order_quantity(item, available=10) == 25  # target 14 + 21 = 35: 25 units, 5 packs


def test_storage_and_cli(tmp_path, capsys):
    path = tmp_path / "inventory.json"
    assert main(["--db", str(path), "add", "W-100", "6"]) == 0
    assert main(["--db", str(path), "reserve", "W-100", "2"]) == 0
    assert storage.load(path).available("W-100") == 4
    capsys.readouterr()
    assert main(["--db", str(path), "show"]) == 0
    assert capsys.readouterr().out == "W-100: 6 on hand, 2 reserved, 4 available\n"
