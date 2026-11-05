"""Hidden checks: reservations record when they were made, the time survives saving and loading
(the CLI round trip), the new command lists open reservations oldest first, and inventories saved
before the change still load."""

import json
from datetime import datetime, timedelta, timezone

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import Inventory


def test_reserve_records_an_aware_utc_time():
    before = datetime.now(timezone.utc)
    inventory = Inventory()
    inventory.add("W-100", 10)
    rid = inventory.reserve("W-100", 4)
    [reservation] = inventory.reservations()
    assert reservation.reservation_id == rid
    assert reservation.created_at.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= reservation.created_at <= datetime.now(timezone.utc) + timedelta(seconds=1)


def test_the_time_survives_saving_and_loading(tmp_path):
    inventory = Inventory()
    inventory.add("W-100", 10)
    inventory.reserve("W-100", 4)
    stamp = inventory.reservations()[0].created_at
    storage.save(inventory, tmp_path / "s.json")
    [loaded] = storage.load(tmp_path / "s.json").reservations()
    assert loaded.created_at == stamp and loaded.quantity == 4


def test_the_cli_round_trip_and_the_reservations_command(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "10"]) == 0
    assert main(["--db", db, "reserve", "W-100", "4"]) == 0
    assert main(["--db", db, "reserve", "W-100", "3"]) == 0
    assert main(["--db", db, "release", "R1"]) == 0
    assert main(["--db", db, "reserve", "W-100", "2"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "reservations"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[:3] for line in lines] == [["R2", "W-100", "3"], ["R3", "W-100", "2"]]
    stamps = [datetime.fromisoformat(line.split()[3]) for line in lines]
    assert all(s.utcoffset() == timedelta(0) for s in stamps) and stamps[0] <= stamps[1]


def test_inventories_saved_before_the_change_still_load(tmp_path):
    old = {"format": 1, "next_id": 2, "on_hand": {"W-100": 10},
           "reservations": [{"reservation_id": "R1", "sku": "W-100", "quantity": 4}]}
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    inventory = storage.load(path)
    assert inventory.available("W-100") == 6
    assert [r.reservation_id for r in inventory.reservations()] == ["R1"]
    storage.save(inventory, tmp_path / "again.json")
    assert storage.load(tmp_path / "again.json").available("W-100") == 6
