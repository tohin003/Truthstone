"""Deprecated: load a spreadsheet stock count (CSV) into an Inventory.

Kept for the pre-0.5 stocktake workflow, which exported counts from a spreadsheet as
``sku,counted`` rows. Stocktakes now go through ``stockroom add``/``remove`` and nothing in
the package imports this module any more; see the CHANGELOG (0.6.0).
"""

from __future__ import annotations

import csv
from pathlib import Path

from stockroom.inventory import Inventory


class CountFileError(ValueError):
    """A count file could not be read. The message names the line."""


def load_counts(path: str | Path) -> Inventory:
    """An inventory holding exactly the counted quantities (no reservations)."""
    inventory = Inventory()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["sku", "counted"]:
            raise CountFileError(f"{path}: expected the header sku,counted")
        for row in reader:
            try:
                counted = int(row["counted"])
            except ValueError:
                raise CountFileError(f"line {reader.line_num}: bad count {row['counted']!r}") from None
            if counted > 0:
                inventory.add(row["sku"].strip(), counted)
    return inventory
