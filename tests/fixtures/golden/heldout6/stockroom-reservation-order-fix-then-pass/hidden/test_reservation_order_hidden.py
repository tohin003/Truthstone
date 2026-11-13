from stockroom.inventory import Inventory


def stocked():
    inventory = Inventory()
    inventory.add("W-100", 100)
    inventory.add("G-200", 100)
    return inventory


def test_oldest_first_across_many_reservations():
    inventory = stocked()
    ids = [inventory.reserve("W-100" if i % 2 else "G-200", 1) for i in range(25)]
    assert [r.reservation_id for r in inventory.reservations()] == ids


def test_oldest_first_for_one_sku():
    inventory = stocked()
    ids = [inventory.reserve("W-100" if i % 3 else "G-200", i + 1) for i in range(14)]
    wanted = [rid for i, rid in enumerate(ids) if i % 3]
    assert [r.reservation_id for r in inventory.reservations("W-100")] == wanted


def test_closed_reservations_drop_out_and_order_holds():
    inventory = stocked()
    ids = [inventory.reserve("W-100", 1) for _ in range(11)]
    inventory.release(ids[0])
    inventory.fulfil(ids[4])
    assert [r.reservation_id for r in inventory.reservations()] == ids[1:4] + ids[5:]


def test_order_survives_a_reload():
    inventory = stocked()
    ids = [inventory.reserve("G-200", 2) for _ in range(12)]
    again = Inventory.from_dict(inventory.to_dict())
    assert [r.reservation_id for r in again.reservations()] == ids
