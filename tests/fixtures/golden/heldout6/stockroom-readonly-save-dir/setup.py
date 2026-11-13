"""Place the back room's live inventory (gitignored, untracked) in shared/, restored from a backup
with its folder left read-only (r-x): loading works, every save fails on the temporary file."""

import json
import os
from pathlib import Path

SKUS = {
    "B-110": 14, "B-220": 3, "C-310": 48, "C-320": 0, "G-200": 9, "G-410": 120,
    "K-501": 6, "K-502": 6, "M-700": 31, "P-150": 75, "S-880": 2, "W-100": 22,
}
RESERVATIONS = [
    {"reservation_id": "R41", "sku": "W-100", "quantity": 4},
    {"reservation_id": "R43", "sku": "G-410", "quantity": 30},
    {"reservation_id": "R44", "sku": "M-700", "quantity": 5},
    {"reservation_id": "R47", "sku": "K-501", "quantity": 2},
    {"reservation_id": "R48", "sku": "P-150", "quantity": 12},
]

shared = Path("shared")
shared.mkdir()
data = {"format": 1, "on_hand": dict(sorted(SKUS.items())), "reservations": RESERVATIONS, "next_id": 49}
(shared / "stockroom.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(shared / "stockroom.json", 0o644)
os.chmod(shared, 0o555)
