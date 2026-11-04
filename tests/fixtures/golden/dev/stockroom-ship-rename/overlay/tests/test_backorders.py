from stockroom.backorders import Backorder, fill, promise, ship_ready
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


def test_ship_ready_ships_what_fill_reserved():
    inventory = Inventory()
    inventory.add("G-200", 5)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("SO-2", "G-200", 1)]
    assert ship_ready(inventory, fill(inventory, queue)) == ["SO-1", "SO-2"]
    assert inventory.on_hand("G-200") == 2
    assert inventory.reservations() == []
