# Changelog

## Unreleased
- Split shipments: `fulfil(reservation_id, quantity)` and `stockroom fulfil R1 --quantity N`
  ship part of a reservation; the rest stays reserved under the same id (#58).

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
