# Changelog

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.

## 0.4.0
- Reservations: `reserve`, `release` and `fulfil`. `available` is on hand minus reserved.
- Removed `Inventory.move()`. It shifted stock between bins without looking at reservations,
  so it could move stock that was already promised. Use `remove()` and `add()` instead.
