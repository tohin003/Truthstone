# Changelog

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.
- Deprecated `stockroom.csv_import` (spreadsheet stock counts): nothing uses it any more; it will
  be removed with its test and sample file.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
