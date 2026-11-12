from stockroom.backorders import Backorder, cancel, fill, promise
from stockroom.inventory import Inventory
from stockroom.models import Order, OrderLine

A1 = Backorder("SO-10", "P-1", 2)
B1 = Backorder("SO-11", "P-1", 1)
B2 = Backorder("SO-11", "P-2", 4)
B3 = Backorder("SO-11", "P-3", 1)
C1 = Backorder("SO-12", "P-2", 1)


def test_every_line_goes_and_comes_back_oldest_first():
    queue = [A1, B1, B2, B3, C1]
    assert cancel(queue, "SO-11") == [B1, B2, B3]
    assert queue == [A1, C1]


def test_lines_spread_through_the_queue_all_go():
    queue = [B1, A1, B2, C1, B3]
    assert cancel(queue, "SO-11") == [B1, B2, B3]
    assert queue == [A1, C1]


def test_cancelling_the_whole_queue_empties_it():
    queue = [B1, B2, B3]
    assert cancel(queue, "SO-11") == [B1, B2, B3]
    assert queue == []


def test_an_order_with_nothing_waiting_changes_nothing():
    queue = [A1, B1, C1]
    assert cancel(queue, "SO-99") == []
    assert queue == [A1, B1, C1]


def test_the_rest_are_still_filled_first_come_first_served():
    inventory = Inventory()
    inventory.add("P-1", 1)
    queue = [Backorder("SO-20", "P-1", 3), Backorder("SO-21", "P-1", 1), Backorder("SO-20", "P-1", 1), Backorder("SO-22", "P-1", 1)]
    cancel(queue, "SO-20")
    filled = fill(inventory, queue)
    assert [backorder.order_id for backorder, _ in filled] == ["SO-21"]
    assert queue == [Backorder("SO-22", "P-1", 1)]


def test_a_new_order_reserves_once_nothing_waits_for_its_sku():
    inventory = Inventory()
    inventory.add("P-5", 2)
    queue = [Backorder("SO-30", "P-5", 5), Backorder("SO-30", "P-5", 1)]
    cancel(queue, "SO-30")
    ids = promise(inventory, Order("SO-31", (OrderLine("P-5", 2),)), queue)
    assert len(ids) == 1 and queue == []
