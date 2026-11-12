import json
from datetime import datetime, timedelta, timezone

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import Inventory


def stocked():
    inventory = Inventory()
    inventory.add("W-100", 10)
    inventory.add("G-200", 5)
    return inventory


def made_at(inventory, reservation_id):
    [reservation] = [r for r in inventory.reservations() if r.reservation_id == reservation_id]
    return reservation.created_at


def test_a_reservation_records_when_it_was_made_in_utc():
    inventory = stocked()
    before = datetime.now(timezone.utc)
    reservation_id = inventory.reserve("W-100", 4)
    after = datetime.now(timezone.utc)
    created = made_at(inventory, reservation_id)
    assert created.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= created <= after + timedelta(seconds=1)


def test_stale_reservations_are_the_open_ones_older_than_the_cutoff_oldest_first():
    inventory = stocked()
    first = inventory.reserve("W-100", 2)
    second = inventory.reserve("G-200", 1)
    released = inventory.reserve("W-100", 1)
    inventory.release(released)
    later = made_at(inventory, second) + timedelta(days=3)
    stale = inventory.stale_reservations(timedelta(days=2), now=later)
    assert [r.reservation_id for r in stale] == [first, second]
    assert list(inventory.stale_reservations(timedelta(days=4), now=later)) == []


def test_stale_reservations_default_to_now():
    inventory = stocked()
    inventory.reserve("W-100", 2)
    assert list(inventory.stale_reservations(timedelta(hours=1))) == []


def test_the_timestamp_survives_save_and_load(tmp_path):
    inventory = stocked()
    reservation_id = inventory.reserve("W-100", 4)
    created = made_at(inventory, reservation_id)
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    json.loads(path.read_text(encoding="utf-8"))
    loaded = storage.load(path)
    restored = made_at(loaded, reservation_id)
    assert abs(restored - created) < timedelta(seconds=1)
    later = created + timedelta(days=3)
    assert [r.reservation_id for r in loaded.stale_reservations(timedelta(days=2), now=later)] == [reservation_id]
    assert loaded.available("W-100") == 6


def test_the_command_line_keeps_the_timestamp(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "10"]) == 0
    assert main(["--db", db, "reserve", "W-100", "4"]) == 0
    assert main(["--db", db, "reserve", "W-100", "1"]) == 0
    assert main(["--db", db, "release", "R2"]) == 0
    loaded = storage.load(db)
    assert [r.reservation_id for r in loaded.reservations()] == ["R1"]
    assert made_at(loaded, "R1").utcoffset() == timedelta(0)


def test_files_saved_before_timestamps_still_load(tmp_path):
    path = tmp_path / "stock.json"
    old = {
        "format": 1,
        "next_id": 3,
        "on_hand": {"G-200": 5, "W-100": 10},
        "reservations": [{"quantity": 4, "reservation_id": "R2", "sku": "W-100"}],
    }
    path.write_text(json.dumps(old), encoding="utf-8")
    loaded = storage.load(path)
    assert loaded.available("W-100") == 6
    assert loaded.reserve("G-200", 1) == "R3"
    loaded.release("R2")
    assert loaded.available("W-100") == 10
    storage.save(loaded, path)
    assert storage.load(path).available("G-200") == 4
