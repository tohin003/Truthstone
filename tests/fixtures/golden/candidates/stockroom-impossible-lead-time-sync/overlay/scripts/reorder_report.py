"""Print the purchase orders to place now: every item at or below its reorder point, and how many to order.

    PYTHONPATH=src python scripts/reorder_report.py [--db stockroom.json]

Demand, safety stock and pack sizes come from data/catalogue.json, lead times from the cached
supplier file data/lead_times.json (see scripts/sync_lead_times.py), stock from the inventory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stockroom import storage
from stockroom.models import Item
from stockroom.reorder import reorder_point, suggestions

DATA = Path(__file__).resolve().parent.parent / "data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reorder_report")
    parser.add_argument("--db", default="stockroom.json")
    args = parser.parse_args(argv)

    catalogue = json.loads((DATA / "catalogue.json").read_text(encoding="utf-8"))
    supplier = json.loads((DATA / "lead_times.json").read_text(encoding="utf-8"))
    items = [
        Item(
            sku=entry["sku"],
            name=entry["name"],
            daily_demand=entry["daily_demand"],
            lead_time_days=supplier["lead_times"][entry["sku"]],
            safety_stock=entry["safety_stock"],
            pack_size=entry["pack_size"],
        )
        for entry in catalogue["items"]
    ]
    inventory = storage.load(args.db)
    orders = suggestions(inventory, items)

    print(f"Lead times: {supplier['supplier']}, {supplier['month']} (fetched {supplier['fetched']})")
    if not orders:
        print("Nothing to reorder.")
        return 0
    print(f"{'SKU':<8} {'item':<26} {'available':>9} {'reorder at':>10} {'order':>6}")
    for item in items:
        if item.sku in orders:
            print(
                f"{item.sku:<8} {item.name:<26} {inventory.available(item.sku):>9} "
                f"{reorder_point(item):>10} {orders[item.sku]:>6}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
