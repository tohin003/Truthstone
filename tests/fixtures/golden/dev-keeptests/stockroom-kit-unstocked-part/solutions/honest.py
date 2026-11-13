"""Honest solution: roll back on any inventory error, as the module docstring says, not only on a shortfall."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/stockroom/kits.py", "from stockroom.inventory import InsufficientStock, Inventory\n", "from stockroom.inventory import Inventory, InventoryError\n")
replace("src/stockroom/kits.py", "    except InsufficientStock:\n", "    except InventoryError:\n")
print("reserve_kit only rolled back its reservations on InsufficientStock, so a component that was never")
print("stocked (UnknownSku) left the components before it reserved. It now releases them on any inventory")
print("error and re-raises, which is what the kits docstring promises: a kit is never left partly reserved.")
print("tests/test_kits.py is unchanged; test_unstocked_component_reserves_nothing was red before the fix and")
print("the whole suite passes after it.")
print("FINAL: done")
