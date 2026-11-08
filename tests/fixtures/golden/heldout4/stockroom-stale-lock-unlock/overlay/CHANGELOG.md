# Changelog

## 0.7.0
- Commands lock the inventory file while they run (`stockroom.json.lock`).
- `scripts/unlock.sh` clears what an interrupted command leaves behind.

## 0.6.1
- Saving writes to a temporary file first, so a crash never leaves a half-written inventory.

## 0.6.0
- Backorders: lines that cannot be reserved are queued and filled first-come, first-served.

## 0.5.0
- Kits reserve all of their components or none.
- Reorder quantities round up to whole supplier packs.
