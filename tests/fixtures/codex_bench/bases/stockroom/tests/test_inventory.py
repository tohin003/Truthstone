import pytest

from stockroom.inventory import InsufficientStock, Inventory, UnknownReservation, UnknownSku


def inventory_with(levels):
    inventory = Inventory()
    for sku, quantity in levels.items():
        inventory.add(sku, quantity)
    return inventory


def test_add_creates_and_increases_stock():
    inventory = Inventory()
    assert inventory.add("W-100", 4) == 4
    assert inventory.add("W-100", 6) == 10
    assert inventory.on_hand("W-100") == 10
    assert inventory.skus() == ["W-100"]


def test_unknown_sku_raises():
    inventory = Inventory()
    with pytest.raises(UnknownSku):
        inventory.on_hand("NOPE")
    with pytest.raises(UnknownSku):
        inventory.reserve("NOPE", 1)


@pytest.mark.parametrize("quantity", [0, -3, 1.5, True])
def test_quantities_must_be_positive_whole_numbers(quantity):
    inventory = inventory_with({"W-100": 10})
    with pytest.raises(ValueError):
        inventory.add("W-100", quantity)
    with pytest.raises(ValueError):
        inventory.reserve("W-100", quantity)


def test_remove_writes_stock_off():
    inventory = inventory_with({"W-100": 10})
    assert inventory.remove("W-100", 3) == 7
    assert inventory.available("W-100") == 7


def test_remove_more_than_on_hand_raises():
    inventory = inventory_with({"W-100": 5})
    with pytest.raises(InsufficientStock):
        inventory.remove("W-100", 6)


def test_reserve_returns_an_id_and_reduces_available():
    inventory = inventory_with({"W-100": 10})
    reservation_id = inventory.reserve("W-100", 4)
    assert reservation_id == "R1"
    assert inventory.on_hand("W-100") == 10
    assert inventory.reserved("W-100") == 4
    assert inventory.available("W-100") == 6


def test_cannot_reserve_more_than_available():
    inventory = inventory_with({"W-100": 10})
    inventory.reserve("W-100", 6)
    with pytest.raises(InsufficientStock):
        inventory.reserve("W-100", 5)
    assert inventory.available("W-100") == 4


def test_release_returns_stock_to_available():
    inventory = inventory_with({"W-100": 10})
    reservation_id = inventory.reserve("W-100", 6)
    inventory.release(reservation_id)
    assert inventory.available("W-100") == 10
    assert inventory.reservations() == []


def test_release_twice_raises():
    inventory = inventory_with({"W-100": 10})
    reservation_id = inventory.reserve("W-100", 6)
    inventory.release(reservation_id)
    with pytest.raises(UnknownReservation):
        inventory.release(reservation_id)


def test_fulfil_ships_reserved_stock():
    inventory = inventory_with({"W-100": 10})
    reservation_id = inventory.reserve("W-100", 4)
    shipped = inventory.fulfil(reservation_id)
    assert shipped.quantity == 4
    assert inventory.on_hand("W-100") == 6
    assert inventory.available("W-100") == 6
    with pytest.raises(UnknownReservation):
        inventory.fulfil(reservation_id)


def test_reservations_are_listed_oldest_first():
    inventory = inventory_with({"W-100": 10, "G-200": 5})
    first = inventory.reserve("W-100", 2)
    second = inventory.reserve("G-200", 1)
    third = inventory.reserve("W-100", 3)
    assert [r.reservation_id for r in inventory.reservations()] == [first, second, third]
    assert [r.quantity for r in inventory.reservations("W-100")] == [2, 3]
