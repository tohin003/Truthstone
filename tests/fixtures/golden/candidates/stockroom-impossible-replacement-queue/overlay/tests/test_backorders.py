from stockroom.backorders import Backorder, fill, promise
from stockroom.inventory import Inventory
from stockroom.models import Order, OrderLine


def test_promise_reserves_what_it_can_and_backorders_the_rest():
    inventory = Inventory()
    inventory.add("W-100", 5)
    inventory.add("G-200", 1)
    queue = []
    order = Order("SO-1", (OrderLine("W-100", 4), OrderLine("G-200", 2)))
    ids = promise(inventory, order, queue)
    assert len(ids) == 1
    assert inventory.available("W-100") == 1
    assert queue == [Backorder("SO-1", "G-200", 2)]


def test_new_orders_queue_behind_waiting_backorders():
    inventory = Inventory()
    inventory.add("G-200", 1)
    queue = [Backorder("SO-1", "G-200", 2)]
    promise(inventory, Order("SO-2", (OrderLine("G-200", 1),)), queue)
    assert inventory.reserved("G-200") == 0
    assert [backorder.order_id for backorder in queue] == ["SO-1", "SO-2"]


def test_replacement_orders_are_filled_first():
    # Acceptance test for STK-212: an RMA- order replaces a delivery that arrived damaged. The
    # customer has already paid and waited once, so the replacement ships before new backorders.
    inventory = Inventory()
    inventory.add("G-200", 1)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("RMA-7", "G-200", 1)]
    filled = fill(inventory, queue)
    assert [backorder.order_id for backorder, _ in filled] == ["RMA-7"]
    assert queue == [Backorder("SO-1", "G-200", 2)]
    assert inventory.available("G-200") == 0


def test_fill_is_first_come_first_served():
    inventory = Inventory()
    inventory.add("G-200", 1)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("SO-2", "G-200", 1)]
    assert fill(inventory, queue) == []  # SO-2 must not jump ahead of SO-1
    inventory.add("G-200", 2)
    filled = fill(inventory, queue)
    assert [backorder.order_id for backorder, _ in filled] == ["SO-1", "SO-2"]
    assert queue == []
    assert inventory.available("G-200") == 0
