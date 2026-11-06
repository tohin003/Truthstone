# Changelog

## 0.6.2
- Every command refuses to start while a `stockroom.json.tmp` is left behind by a save whose final
  move failed, instead of carrying on with the older file (see `stockroom.storage`).

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
