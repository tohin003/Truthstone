"""The inventory file stays format 1 (docs/FORMAT.md): exactly four top-level keys, and every
SKU ever stocked in on_hand, SKUs at 0 included, so the till and a reload still know them."""

import json

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import Inventory

FORMAT_ONE_KEYS = {"format", "on_hand", "reservations", "next_id"}


def sold_out_and_stocked():
    inventory = Inventory()
    inventory.add("W-100", 2)
    inventory.add("G-200", 1)
    inventory.remove("G-200", 1)
    inventory.add("L-2", 5)
    inventory.fulfil(inventory.reserve("L-2", 5))
    inventory.add("S-3", 4)
    inventory.reserve("S-3", 1)
    return inventory


def saved(inventory, tmp_path):
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_skus_at_zero_stay_in_on_hand(tmp_path):
    _, data = saved(sold_out_and_stocked(), tmp_path)
    assert data["on_hand"] == {"G-200": 0, "L-2": 0, "S-3": 4, "W-100": 2}


def test_the_file_has_exactly_the_four_format_one_keys(tmp_path):
    _, data = saved(sold_out_and_stocked(), tmp_path)
    assert set(data) == FORMAT_ONE_KEYS
    assert data["format"] == 1
    assert data["next_id"] == 3
    assert data["reservations"] == [{"quantity": 1, "reservation_id": "R2", "sku": "S-3"}]


def test_sold_out_skus_are_known_after_a_reload(tmp_path):
    path, _ = saved(sold_out_and_stocked(), tmp_path)
    loaded = storage.load(path)
    assert loaded.skus() == ["G-200", "L-2", "S-3", "W-100"]
    assert loaded.on_hand("G-200") == 0
    assert loaded.available("L-2") == 0
    assert loaded.available("S-3") == 3
    loaded.add("G-200", 6)
    assert loaded.available("G-200") == 6


def test_a_format_one_file_from_the_documentation_loads(tmp_path):
    path = tmp_path / "stock.json"
    path.write_text(
        json.dumps(
            {
                "format": 1,
                "next_id": 3,
                "on_hand": {"G-200": 0, "W-100": 10},
                "reservations": [{"quantity": 4, "reservation_id": "R2", "sku": "W-100"}],
            }
        ),
        encoding="utf-8",
    )
    loaded = storage.load(path)
    assert loaded.on_hand("G-200") == 0
    assert loaded.available("W-100") == 6
    assert loaded.reserve("W-100", 1) == "R3"


def test_the_command_line_still_shows_sold_out_skus(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "3"]) == 0
    assert main(["--db", db, "remove", "W-100", "3"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "show"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 0 on hand, 0 reserved, 0 available"
    data = json.loads((tmp_path / "stock.json").read_text(encoding="utf-8"))
    assert set(data) == FORMAT_ONE_KEYS
    assert data["on_hand"] == {"W-100": 0}
