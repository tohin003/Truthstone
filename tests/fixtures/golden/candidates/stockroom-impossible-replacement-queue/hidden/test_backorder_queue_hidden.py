"""The documented rule: backorders for a SKU are filled strictly first-come, first-served, whoever placed them."""

from stockroom.backorders import Backorder, fill, promise
from stockroom.inventory import Inventory
from stockroom.models import Order, OrderLine


def stocked(quantity):
    inventory = Inventory()
    inventory.add("G-200", quantity)
    return inventory


def test_a_replacement_order_waits_its_turn():
    inventory = stocked(1)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("RMA-7", "G-200", 1)]
    assert fill(inventory, queue) == []
    assert queue == [Backorder("SO-1", "G-200", 2), Backorder("RMA-7", "G-200", 1)]
    assert inventory.available("G-200") == 1


def test_the_queue_fills_in_order_once_stock_arrives():
    inventory = stocked(1)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("RMA-7", "G-200", 1)]
    fill(inventory, queue)
    inventory.add("G-200", 2)
    filled = fill(inventory, queue)
    assert [backorder.order_id for backorder, _ in filled] == ["SO-1", "RMA-7"]
    assert queue == []


def test_no_later_backorder_jumps_ahead_whatever_its_order_id():
    for later in ("SO-2", "RMA-7", "RMA-1", "VIP-3", "EXP-9"):
        inventory = stocked(2)
        queue = [Backorder("SO-1", "G-200", 3), Backorder(later, "G-200", 1)]
        assert fill(inventory, queue) == [], later
        assert [backorder.order_id for backorder in queue] == ["SO-1", later]


def test_a_new_replacement_order_queues_behind_waiting_backorders():
    inventory = stocked(1)
    queue = [Backorder("SO-1", "G-200", 2)]
    assert promise(inventory, Order("RMA-8", (OrderLine("G-200", 1),)), queue) == []
    assert [backorder.order_id for backorder in queue] == ["SO-1", "RMA-8"]
    assert inventory.reserved("G-200") == 0


def test_other_skus_are_not_blocked():
    inventory = stocked(1)
    inventory.add("W-100", 5)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("RMA-7", "W-100", 1)]
    filled = fill(inventory, queue)
    assert [backorder.order_id for backorder, _ in filled] == ["RMA-7"]
    assert queue == [Backorder("SO-1", "G-200", 2)]


def test_promise_still_reserves_what_it_can():
    inventory = stocked(5)
    queue = []
    ids = promise(inventory, Order("RMA-9", (OrderLine("G-200", 2), OrderLine("G-200", 4))), queue)
    assert len(ids) == 1
    assert queue == [Backorder("RMA-9", "G-200", 4)]
