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

## Purchase orders

Lead times are the supplier's, not ours. `python scripts/sync_lead_times.py [YYYY-MM]`
downloads Ningbo Supply's figures for a month from their portal into `data/lead_times.json`;
cron runs it at 06:00 on the 1st, and we run it by hand when they announce changes. If the
portal cannot be reached it keeps the cached file and says so on stderr, but it exits 0 so an
outage does not page anyone. Never edit `data/lead_times.json` by hand: Ningbo checks every
purchase order against the lead times it published.

    PYTHONPATH=src python scripts/reorder_report.py

prints the purchase orders to place now (each item at or below its reorder point, and the
quantity), from `data/catalogue.json`, the cached lead times (its first line names the month
they are for) and the stock in `stockroom.json`.

## Command line

    stockroom add W-100 10
    stockroom reserve W-100 4      # prints the reservation id
    stockroom release R1
    stockroom fulfil R2
    stockroom show [SKU]

State is kept in `stockroom.json` in the current directory; `--db PATH` uses another file.
