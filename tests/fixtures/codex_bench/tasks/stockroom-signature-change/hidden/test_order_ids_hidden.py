"""Every way of reserving stock records the order it is for."""

import pytest

from stockroom import storage
from stockroom.backorders import Backorder, fill, promise
from stockroom.cli import main
from stockroom.inventory import InsufficientStock, Inventory
from stockroom.kits import Kit, reserve_kit
from stockroom.models import Order, OrderLine


def stocked(levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku, quantity)
    return inventory


def test_reserve_takes_a_required_keyword_only_order_id():
    inventory = stocked({"W-1": 5})
    reservation_id = inventory.reserve("W-1", 2, order_id="SO-1")
    (reservation,) = inventory.reservations()
    assert reservation.reservation_id == reservation_id
    assert reservation.order_id == "SO-1"
    with pytest.raises(TypeError):
        inventory.reserve("W-1", 1)
    with pytest.raises(TypeError):
        inventory.reserve("W-1", 1, "SO-2")
    assert inventory.reserved("W-1") == 2


def test_order_ids_survive_save_and_load(tmp_path):
    inventory = stocked({"W-1": 5})
    inventory.reserve("W-1", 2, order_id="SO-7")
    path = tmp_path / "stock.json"
    storage.save(inventory, path)
    loaded = storage.load(path)
    assert [(r.sku, r.quantity, r.order_id) for r in loaded.reservations()] == [("W-1", 2, "SO-7")]


def test_reserve_kit_passes_the_order_id_through():
    inventory = stocked({"D-1": 2, "L-2": 8})
    kit = Kit("desk set", {"D-1": 1, "L-2": 2})
    ids = reserve_kit(inventory, kit, count=2, order_id="SO-9")
    assert len(ids) == 2
    assert sorted((r.sku, r.quantity, r.order_id) for r in inventory.reservations()) == [
        ("D-1", 2, "SO-9"),
        ("L-2", 4, "SO-9"),
    ]


def test_reserve_kit_still_rolls_back():
    inventory = stocked({"D-1": 2, "L-2": 3})
    kit = Kit("desk set", {"D-1": 1, "L-2": 2})
    with pytest.raises(InsufficientStock):
        reserve_kit(inventory, kit, count=2, order_id="SO-9")
    assert inventory.reservations() == []


def test_promise_and_fill_tag_reservations_with_their_orders():
    inventory = stocked({"W-1": 5, "G-2": 1})
    queue = [Backorder("SO-0", "G-2", 1)]
    promise(inventory, Order("SO-1", (OrderLine("W-1", 4), OrderLine("G-2", 2))), queue)
    assert [(r.sku, r.order_id) for r in inventory.reservations()] == [("W-1", "SO-1")]
    inventory.add("G-2", 2)
    filled = fill(inventory, queue)
    assert [backorder.order_id for backorder, _ in filled] == ["SO-0", "SO-1"]
    assert [(r.sku, r.quantity, r.order_id) for r in inventory.reservations()] == [
        ("W-1", 4, "SO-1"),
        ("G-2", 1, "SO-0"),
        ("G-2", 2, "SO-1"),
    ]


# The request leaves the command-line spelling open; accept any reasonable one.
RESERVE_FORMS = (
    ["reserve", "W-1", "2", "--order", "SO-5"],
    ["reserve", "--order", "SO-5", "W-1", "2"],
    ["reserve", "W-1", "2", "--order-id", "SO-5"],
    ["reserve", "W-1", "2", "--order_id", "SO-5"],
    ["reserve", "W-1", "2", "-o", "SO-5"],
    ["reserve", "W-1", "2", "SO-5"],
    ["reserve", "SO-5", "W-1", "2"],
    ["--order", "SO-5", "reserve", "W-1", "2"],
)


def test_the_cli_reserve_command_records_the_order(tmp_path, capsys):
    problems = []
    for number, form in enumerate(RESERVE_FORMS):
        db = str(tmp_path / f"stock-{number}.json")
        assert main(["--db", db, "add", "W-1", "5"]) == 0
        try:
            code = main(["--db", db, *form])
        except SystemExit as exc:
            problems.append(f"{form}: exit {exc.code}")
            continue
        except Exception as exc:  # a stale call site fails here, e.g. with TypeError
            problems.append(f"{form}: {type(exc).__name__}: {exc}")
            continue
        recorded = [r.order_id for r in storage.load(db).reservations()]
        if code == 0 and recorded == ["SO-5"]:
            return
        problems.append(f"{form}: exit {code}, recorded {recorded}")
    capsys.readouterr()
    pytest.fail("no way to record an order id through `stockroom reserve`:\n" + "\n".join(problems))


def test_the_other_cli_stock_commands_still_work(tmp_path):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-1", "5"]) == 0
    assert main(["--db", db, "remove", "W-1", "2"]) == 0
    assert storage.load(db).on_hand("W-1") == 3
