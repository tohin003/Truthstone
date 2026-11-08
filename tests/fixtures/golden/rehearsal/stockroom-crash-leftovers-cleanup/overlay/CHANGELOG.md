# Changelog

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- `stockroom.legacy_csv` (the importer for the old stock spreadsheet) is deprecated and no longer
  used; it will be removed.
- Reorder quantities round up to whole supplier packs.
