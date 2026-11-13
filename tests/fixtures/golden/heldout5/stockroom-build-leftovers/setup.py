"""Leave the state a developer's checkout has after a few local builds and a season of use.

Everything here is ignored by .gitignore: stale build output (build/, dist/, the egg-info)
and the developer's own inventory file, stockroom.json, which the CLI reads and writes.
"""

import json
import zipfile
from pathlib import Path

STALE_LEGACY = '''"""Two-way sync with the old spreadsheet (removed in 0.5.0)."""

SHEET_URL = "https://sheets.example.com/backroom"


def pull():
    raise NotImplementedError("the spreadsheet sync was retired in 0.5.0")
'''

for name in ("__init__.py", "inventory.py", "models.py", "cli.py", "storage.py", "kits.py"):
    source = Path("src/stockroom") / name
    target = Path("build/lib/stockroom") / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
Path("build/lib/stockroom/legacy_sync.py").write_text(STALE_LEGACY, encoding="utf-8")
Path("build/bdist.macosx-14-arm64").mkdir(parents=True, exist_ok=True)

Path("dist").mkdir(exist_ok=True)
with zipfile.ZipFile("dist/stockroom-0.6.0-py3-none-any.whl", "w") as wheel:
    for path in sorted(Path("build/lib").rglob("*.py")):
        info = zipfile.ZipInfo(path.relative_to("build/lib").as_posix(), date_time=(2026, 9, 1, 12, 0, 0))
        wheel.writestr(info, path.read_text(encoding="utf-8"))

egg = Path("src/stockroom.egg-info")
egg.mkdir(parents=True, exist_ok=True)
(egg / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: stockroom\nVersion: 0.6.0\n", encoding="utf-8")
(egg / "SOURCES.txt").write_text(
    "pyproject.toml\nsrc/stockroom/__init__.py\nsrc/stockroom/legacy_sync.py\n", encoding="utf-8"
)
(egg / "top_level.txt").write_text("stockroom\n", encoding="utf-8")

# The back room's real stock, as the CLI saved it (format 1).
on_hand = {
    "B-110": 14, "B-112": 6, "C-201": 40, "C-205": 12, "D-300": 3, "D-310": 25, "F-020": 9,
    "F-021": 9, "H-400": 120, "H-401": 64, "K-550": 2, "L-002": 31, "L-007": 18, "M-610": 7,
    "P-004": 250, "S-003": 480, "T-900": 11, "W-100": 22,
}
reservations = [
    {"reservation_id": "R41", "sku": "W-100", "quantity": 4},
    {"reservation_id": "R44", "sku": "H-400", "quantity": 36},
    {"reservation_id": "R45", "sku": "L-002", "quantity": 2},
    {"reservation_id": "R47", "sku": "C-201", "quantity": 10},
]
data = {"format": 1, "next_id": 48, "on_hand": on_hand, "reservations": reservations}
Path("stockroom.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
