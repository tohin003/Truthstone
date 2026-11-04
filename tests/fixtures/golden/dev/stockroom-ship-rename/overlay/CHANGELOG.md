# Changelog

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.
- `backorders.ship_ready` ships the reservations that `fill` made.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.
- The `release` and `fulfil` commands are generated from `RESERVATION_COMMANDS` in cli.py and
  call the Inventory method of the same name.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
