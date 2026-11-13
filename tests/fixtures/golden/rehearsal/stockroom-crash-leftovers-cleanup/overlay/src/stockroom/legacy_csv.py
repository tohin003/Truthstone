"""Import stock levels from the old stock spreadsheet's CSV export (before 0.5).

Deprecated since 0.5: stock lives in stockroom.json now, and nothing in the package imports this
module any more.
"""

from __future__ import annotations

import csv
from pathlib import Path

from stockroom.inventory import Inventory


def load_spreadsheet(path: str | Path) -> Inventory:
    """An inventory with the spreadsheet's on-hand levels; rows with no stock are skipped."""
    inventory = Inventory()
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            quantity = int(row["Qty"] or 0)
            if quantity > 0:
                inventory.add(row["SKU"].strip(), quantity)
    return inventory
