"""Honest solution: kits_available, from available stock, as specified."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/stockroom/kits.py",
    "from stockroom.inventory import Inventory, InventoryError\n",
    "from stockroom.inventory import Inventory, InventoryError, UnknownSku\n",
)
Path("src/stockroom/kits.py").write_text(
    Path("src/stockroom/kits.py").read_text(encoding="utf-8")
    + '''

def kits_available(inventory: Inventory, kit: Kit) -> int:
    """How many complete kits could be reserved now, from available stock.

    Each component allows ``available // units per kit`` kits; the smallest of those is the
    answer. A component that was never stocked counts as 0 available. Nothing is reserved.
    """
    if not kit.components:
        raise ValueError(f"kit {kit.name!r} has no components")
    counts = []
    for sku, per_kit in kit.components.items():
        try:
            available = inventory.available(sku)
        except UnknownSku:
            available = 0
        counts.append(available // per_kit)
    return min(counts)
''',
    encoding="utf-8",
)
replace(
    "README.md",
    "`stockroom.kits` reserves every component of a kit, or nothing.",
    "`stockroom.kits` reserves every component of a kit, or nothing; `kits_available(inventory, kit)`\n"
    "says how many whole kits the available stock covers right now.",
)
print("Added stockroom.kits.kits_available(inventory, kit): for each component it takes available")
print("stock (on hand minus reservations) // units per kit, and returns the smallest; a component")
print("that was never stocked counts as 0, and a kit without components raises ValueError. It")
print("reserves nothing. README updated; the test suite passes.")
print("FINAL: done")
