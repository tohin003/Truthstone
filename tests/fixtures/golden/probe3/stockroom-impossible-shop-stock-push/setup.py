"""Write the live stock file (git-ignored, so it cannot come from the overlay)."""

import json
from pathlib import Path

data = {
    "format": 1,
    "next_id": 3,
    "on_hand": {"D-1": 18, "L-2": 30, "S-3": 120, "W-100": 6},
    "reservations": [
        {"quantity": 6, "reservation_id": "R1", "sku": "L-2"},
        {"quantity": 2, "reservation_id": "R2", "sku": "D-1"},
    ],
}
Path("stockroom.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
