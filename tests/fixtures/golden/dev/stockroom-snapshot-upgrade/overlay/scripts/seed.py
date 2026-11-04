"""Write a small demo inventory for trying the CLI locally.

    python scripts/seed.py            # writes var/stock.json; refuses to replace an existing file
    python scripts/seed.py --force    # replaces it
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockroom import storage  # noqa: E402
from stockroom.inventory import Inventory  # noqa: E402

DEMO_STOCK = {"W-100": 40, "G-200": 12, "D-1": 3, "L-2": 14, "S-3": 120}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a demo inventory.")
    parser.add_argument("--path", default="var/stock.json")
    parser.add_argument("--force", action="store_true", help="replace an existing file")
    args = parser.parse_args(argv)
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"{path} already exists; pass --force to replace it", file=sys.stderr)
        return 1
    inventory = Inventory()
    for sku, quantity in DEMO_STOCK.items():
        inventory.add(sku, quantity)
    inventory.reserve("L-2", 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    storage.save(inventory, path)
    print(f"wrote a demo inventory to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
