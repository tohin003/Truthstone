"""#71 as documented: an order's waiting lines are filled together, oldest order first, and a
waiting order keeps its place for each of its SKUs; orders needing none of them are filled."""

from stockroom.backorders import Backorder, fill
from stockroom.inventory import Inventory


def stocked(**levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku.replace("_", "-"), quantity)
    return inventory


def ids(filled):
    return [(backorder.order_id, backorder.sku) for backorder, _ in filled]


def test_a_waiting_order_holds_every_one_of_its_skus():
    inventory = stocked(W_100=1, G_200=1)
    queue = [Backorder("SO-1", "G-200", 1), Backorder("SO-1", "W-100", 3), Backorder("SO-2", "G-200", 1)]
    assert fill(inventory, queue) == []
    assert inventory.reservations() == []
    assert len(queue) == 3


def test_the_held_sku_goes_to_the_waiting_order_once_it_can_ship():
    inventory = stocked(W_100=1, G_200=1)
    queue = [Backorder("SO-1", "W-100", 1), Backorder("SO-1", "G-200", 2), Backorder("SO-2", "W-100", 1)]
    assert fill(inventory, queue) == []
    inventory.add("G-200", 1)
    inventory.add("W-100", 1)
    assert ids(fill(inventory, queue)) == [("SO-1", "W-100"), ("SO-1", "G-200"), ("SO-2", "W-100")]
    assert queue == []
    assert inventory.available("W-100") == 0
    assert inventory.available("G-200") == 0


def test_orders_needing_other_skus_are_still_filled():
    inventory = stocked(W_100=5, G_200=1, K_300=2)
    queue = [Backorder("SO-1", "W-100", 1), Backorder("SO-1", "G-200", 2), Backorder("SO-2", "K-300", 2)]
    assert ids(fill(inventory, queue)) == [("SO-2", "K-300")]
    assert queue == [Backorder("SO-1", "W-100", 1), Backorder("SO-1", "G-200", 2)]
    assert inventory.reserved("W-100") == 0


def test_whole_orders_fill_and_leave_the_queue():
    inventory = stocked(W_100=4, G_200=4)
    queue = [Backorder("SO-1", "W-100", 2), Backorder("SO-1", "G-200", 1), Backorder("SO-2", "W-100", 2)]
    filled = fill(inventory, queue)
    assert ids(filled) == [("SO-1", "W-100"), ("SO-1", "G-200"), ("SO-2", "W-100")]
    assert queue == []
    assert sorted(r.reservation_id for r in inventory.reservations()) == sorted(rid for _, rid in filled)


def test_single_sku_queue_is_still_first_come_first_served():
    inventory = stocked(G_200=1)
    queue = [Backorder("SO-1", "G-200", 2), Backorder("SO-2", "G-200", 1)]
    assert fill(inventory, queue) == []
    inventory.add("G-200", 2)
    assert ids(fill(inventory, queue)) == [("SO-1", "G-200"), ("SO-2", "G-200")]
