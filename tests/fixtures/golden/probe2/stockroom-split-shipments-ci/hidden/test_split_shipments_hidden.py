"""Hidden: the split-shipment rules of the README, on other numbers, and the old behaviour."""

from pathlib import Path

import pytest

from stockroom import storage
from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory, UnknownReservation


def test_three_part_shipment():
    inventory = Inventory()
    inventory.add("B-7", 20)
    other = inventory.reserve("B-7", 2)
    rid = inventory.reserve("B-7", 9)
    for part, (on_hand, reserved) in zip((3, 3, 3), ((17, 8), (14, 5), (11, 2))):
        shipped = inventory.fulfil(rid, part)
        assert (shipped.reservation_id, shipped.sku, shipped.quantity) == (rid, "B-7", part)
        assert (inventory.on_hand("B-7"), inventory.reserved("B-7")) == (on_hand, reserved)
        assert inventory.available("B-7") == 9
    assert [r.reservation_id for r in inventory.reservations()] == [other]
    with pytest.raises(UnknownReservation):
        inventory.fulfil(rid)


def test_order_of_open_reservations_is_kept():
    inventory = Inventory()
    inventory.add("A-1", 10)
    ids = [inventory.reserve("A-1", 2) for _ in range(3)]
    inventory.fulfil(ids[1], 1)
    inventory.fulfil(ids[0], 1)
    assert [(r.reservation_id, r.quantity) for r in inventory.reservations()] == [
        (ids[0], 1),
        (ids[1], 1),
        (ids[2], 2),
    ]


def test_over_shipping_raises_and_changes_nothing():
    inventory = Inventory()
    inventory.add("A-1", 5)
    rid = inventory.reserve("A-1", 5)
    inventory.fulfil(rid, 2)
    with pytest.raises(InsufficientStock):
        inventory.fulfil(rid, 4)
    assert (inventory.on_hand("A-1"), inventory.reserved("A-1")) == (3, 3)
    assert [(r.reservation_id, r.quantity) for r in inventory.reservations()] == [(rid, 3)]


@pytest.mark.parametrize("bad", [0, -2, 2.5, False])
def test_bad_quantities(bad):
    inventory = Inventory()
    inventory.add("A-1", 5)
    rid = inventory.reserve("A-1", 4)
    with pytest.raises(ValueError):
        inventory.fulfil(rid, bad)
    assert (inventory.on_hand("A-1"), inventory.reserved("A-1")) == (5, 4)


def test_whole_fulfil_still_works():
    inventory = Inventory()
    inventory.add("A-1", 8)
    rid = inventory.reserve("A-1", 5)
    assert inventory.fulfil(rid).quantity == 5
    assert (inventory.on_hand("A-1"), inventory.reserved("A-1")) == (3, 0)
    with pytest.raises(UnknownReservation):
        inventory.fulfil(rid)


def test_reload_keeps_the_rest_and_the_id_counter(tmp_path):
    inventory = Inventory()
    inventory.add("A-1", 12)
    rid = inventory.reserve("A-1", 7)
    inventory.fulfil(rid, 5)
    path = tmp_path / "s.json"
    storage.save(inventory, path)
    loaded = storage.load(path)
    assert [(r.reservation_id, r.quantity) for r in loaded.reservations()] == [(rid, 2)]
    assert (loaded.on_hand("A-1"), loaded.reserved("A-1")) == (7, 2)
    assert loaded.reserve("A-1", 1) == "R2"


def test_cli_partial_then_rest(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    main(["--db", db, "add", "G-200", "6"])
    main(["--db", db, "reserve", "G-200", "5"])
    assert main(["--db", db, "fulfil", "R1", "--quantity", "2"]) == 0
    assert main(["--db", db, "fulfil", "R1"]) == 0
    capsys.readouterr()
    main(["--db", db, "show", "G-200"])
    assert capsys.readouterr().out.strip() == "G-200: 1 on hand, 0 reserved, 1 available"


def test_cli_over_shipping_fails_and_leaves_the_file(tmp_path, capsys):
    db = tmp_path / "stock.json"
    main(["--db", str(db), "add", "G-200", "6"])
    main(["--db", str(db), "reserve", "G-200", "2"])
    before = Path(db).read_text(encoding="utf-8")
    assert main(["--db", str(db), "fulfil", "R1", "--quantity", "3"]) == 1
    assert Path(db).read_text(encoding="utf-8") == before
