"""Saving and loading an inventory as JSON.

``save`` writes the whole inventory to ``<file>.tmp`` and then moves it over ``<file>`` in one
step, so a crash never leaves a half-written inventory. If the move itself fails (on the
warehouse PC, Windows refuses it while the backup agent has the file open), the ``.tmp`` file
stays behind holding the newest inventory, and ``<file>`` still holds the one before it.

``load`` refuses to read ``<file>`` while ``<file>.tmp`` exists: carrying on would let the next
save overwrite the newer ``.tmp`` and lose whatever was booked in it. A complete ``.tmp`` (valid
JSON with ``"format": 1``) should be moved over ``<file>``; only a truncated one, from a crash in
the middle of writing it, should be deleted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from stockroom.inventory import Inventory

FORMAT_VERSION = 1


class StorageError(Exception):
    """The file is not an inventory this version can read."""


def temporary_path(path: str | Path) -> Path:
    """Where ``save`` writes before moving the file into place: ``<file>.tmp``."""
    path = Path(path)
    return path.with_name(path.name + ".tmp")


def save(inventory: Inventory, path: str | Path) -> None:
    """Write ``inventory`` to ``path``. A crash mid-save never leaves a half-written file."""
    path = Path(path)
    data = {"format": FORMAT_VERSION, **inventory.to_dict()}
    temporary = temporary_path(path)
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load(path: str | Path) -> Inventory:
    path = Path(path)
    leftover = temporary_path(path)
    if leftover.exists():
        raise StorageError(f"refusing to load {path}: {leftover.name} exists (an earlier save did not finish)")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT_VERSION:
        raise StorageError(f"{path}: not a stockroom inventory (format {FORMAT_VERSION})")
    return Inventory.from_dict(data)
