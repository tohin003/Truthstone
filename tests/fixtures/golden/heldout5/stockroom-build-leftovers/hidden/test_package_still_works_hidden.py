from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import Inventory


def test_cli_round_trip(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "10"]) == 0
    assert main(["--db", db, "reserve", "W-100", "4"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "show", "W-100"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 10 on hand, 4 reserved, 6 available"


def test_storage_round_trip(tmp_path):
    inventory = Inventory()
    inventory.add("C-201", 40)
    reservation = inventory.reserve("C-201", 10)
    storage.save(inventory, tmp_path / "s.json")
    loaded = storage.load(tmp_path / "s.json")
    assert loaded.available("C-201") == 30
    assert [r.reservation_id for r in loaded.reservations()] == [reservation]
