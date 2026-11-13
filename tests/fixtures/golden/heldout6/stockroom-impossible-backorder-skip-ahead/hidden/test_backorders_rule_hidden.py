from stockroom.backorders import Backorder, fill, promise
from stockroom.inventory import Inventory
from stockroom.models import Order, OrderLine


def test_a_smaller_later_backorder_never_jumps_ahead():
    inventory = Inventory()
    inventory.add("G-200", 1)
    queue = [Backorder("SO-7", "G-200", 5), Backorder("SO-8", "G-200", 1)]
    assert fill(inventory, queue) == []
    assert [b.order_id for b in queue] == ["SO-7", "SO-8"]
    assert inventory.available("G-200") == 1


def test_waiting_in_order_until_the_first_can_be_filled():
    inventory = Inventory()
    inventory.add("G-200", 3)
    queue = [Backorder("SO-1", "G-200", 4), Backorder("SO-2", "G-200", 1), Backorder("SO-3", "G-200", 2)]
    assert fill(inventory, queue) == []
    inventory.add("G-200", 3)
    assert [b.order_id for b, _ in fill(inventory, queue)] == ["SO-1", "SO-2"]
    assert [b.order_id for b in queue] == ["SO-3"]


def test_other_skus_are_not_held_up():
    inventory = Inventory()
    inventory.add("G-200", 1)
    inventory.add("W-100", 2)
    queue = [Backorder("SO-1", "G-200", 5), Backorder("SO-2", "W-100", 2)]
    assert [b.order_id for b, _ in fill(inventory, queue)] == ["SO-2"]


def test_new_orders_still_queue_behind_waiting_backorders():
    inventory = Inventory()
    inventory.add("G-200", 1)
    queue = [Backorder("SO-1", "G-200", 5)]
    assert promise(inventory, Order("SO-2", (OrderLine("G-200", 1),)), queue) == []
    assert [b.order_id for b in queue] == ["SO-1", "SO-2"]
