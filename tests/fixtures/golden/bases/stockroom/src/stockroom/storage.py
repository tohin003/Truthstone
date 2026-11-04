"""Saving and loading an inventory as JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path

from stockroom.inventory import Inventory

FORMAT_VERSION = 1


class StorageError(Exception):
    """The file is not an inventory this version can read."""


def save(inventory: Inventory, path: str | Path) -> None:
    """Write ``inventory`` to ``path``. A crash mid-save never leaves a half-written file."""
    path = Path(path)
    data = {"format": FORMAT_VERSION, **inventory.to_dict()}
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load(path: str | Path) -> Inventory:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT_VERSION:
        raise StorageError(f"{path}: not a stockroom inventory (format {FORMAT_VERSION})")
    return Inventory.from_dict(data)
