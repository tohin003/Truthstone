# Changelog

## Unreleased
- Items hold `safety_days` (days of demand held back) instead of a fixed `safety_stock`
  count; `reorder.safety_stock(item)` turns it into units.

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
