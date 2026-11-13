# Changelog

## 0.7.0 (unreleased)
- Backorders of one order are filled together (#71): `fill` reserves every waiting line of an
  order or none of them, so a customer never gets half an order and a second shipment. An order
  that is still waiting keeps its place in the queue for each of its SKUs.

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
