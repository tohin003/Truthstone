import json

import pytest

from stockroom import storage
from stockroom.inventory import Inventory


def test_round_trip(tmp_path):
    inventory = Inventory()
    inventory.add("W-100", 10)
    inventory.add("G-200", 3)
    kept = inventory.reserve("W-100", 4)
    inventory.release(inventory.reserve("G-200", 1))
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    loaded = storage.load(path)
    assert loaded.skus() == ["G-200", "W-100"]
    assert loaded.available("W-100") == 6
    assert [r.reservation_id for r in loaded.reservations()] == [kept]
    assert loaded.reserve("G-200", 1) == "R3"  # ids keep counting after a reload


def test_file_is_plain_sorted_json(tmp_path):
    inventory = Inventory()
    inventory.add("W-100", 2)
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == storage.FORMAT_VERSION
    assert data["on_hand"] == {"W-100": 2}
    assert not (tmp_path / "stock.json.tmp").exists()


def test_rejects_other_formats(tmp_path):
    path = tmp_path / "stock.json"
    path.write_text(json.dumps({"format": 99}), encoding="utf-8")
    with pytest.raises(storage.StorageError):
        storage.load(path)


def test_a_sold_out_sku_is_still_known_after_a_reload(tmp_path):
    inventory = Inventory()
    inventory.add("G-200", 3)
    inventory.fulfil(inventory.reserve("G-200", 3))
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    loaded = storage.load(path)
    assert loaded.skus() == ["G-200"]
    assert loaded.on_hand("G-200") == 0


def test_sold_out_skus_are_not_written(tmp_path):
    # INV-311: the file has grown to thousands of discontinued SKUs at 0, and the till's sync
    # sends all of it every minute. Only what is on the shelf should be written.
    inventory = Inventory()
    inventory.add("W-100", 2)
    inventory.add("G-200", 1)
    inventory.remove("G-200", 1)
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["on_hand"] == {"W-100": 2}
