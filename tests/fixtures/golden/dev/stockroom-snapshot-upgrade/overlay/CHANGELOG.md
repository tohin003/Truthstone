# Changelog

## Unreleased
- Inventory files are storage format 2: one record per SKU under `items`, reservations as
  `{"id", "sku", "quantity"}` and `next_reservation`, so per-SKU settings can follow.
  Format 1 files (a flat `on_hand` map, `reservation_id` keys, `next_id`) are not read
  any more; there is no upgrade path yet.
- `scripts/seed.py` writes a demo inventory to `var/stock.json`.

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
