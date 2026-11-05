# stockroom

Stock levels, reservations, kits, backorders and reorder suggestions for the shop's
back room.

## Stock and reservations

```python
from stockroom.inventory import Inventory

inventory = Inventory()
inventory.add("W-100", 10)                      # receive stock
reservation_id = inventory.reserve("W-100", 4)  # earmark 4 units for an order: "R1"
inventory.available("W-100")                    # 6
inventory.release(reservation_id)               # cancel it: 10 available again
```

- `on_hand` is what is physically on the shelf. `available` is what can still be
  promised: `on_hand` minus active reservations.
- Reserving or writing off (`remove`) more than is available raises `InsufficientStock`.
- `fulfil(reservation_id)` ships a reservation and `release` cancels it. Either one closes
  the reservation; a closed reservation cannot be released or fulfilled again.

`stockroom.kits` reserves every component of a kit, or nothing. `stockroom.backorders`
queues order lines that cannot be reserved yet and fills them first-come, first-served.

## Reordering

`stockroom.reorder` works from each item's average daily demand, supplier lead time,
safety stock and pack size:

    reorder point = ceil(daily demand × lead time in days) + safety stock

An item is reordered when its available stock is at or below its reorder point. The
order brings available stock up to `reorder point + ceil(daily demand × 7)` (one review
period of cover), rounded up to whole packs.

## Command line

    stockroom add W-100 10
    stockroom reserve W-100 4      # prints the reservation id
    stockroom release R1
    stockroom fulfil R2
    stockroom show [SKU]

State is kept in `stockroom.json` in the current directory; `--db PATH` uses another file.

## Tests

`pytest` runs the unit tests. The integration tests (`tests/test_cli.py`, `tests/test_storage.py`:
round trips through real files) are deselected by default; CI runs them with `pytest -m integration`.
