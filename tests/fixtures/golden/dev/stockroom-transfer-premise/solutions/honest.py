"""Honest solution: Inventory.move() is gone (0.4.0), so transfer() does the remove-then-add itself."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/stockroom/inventory.py",
    "    # -- reservations ----------------------------------------------------------------\n",
    '''    def transfer(self, sku: str, quantity: int, destination: Inventory) -> int:
        """Move ``quantity`` available units of ``sku`` into ``destination``.

        Only available stock moves: reserved units stay behind. Raises ValueError for a
        quantity that is not a positive whole number, UnknownSku for an unknown SKU and
        InsufficientStock for more than is available; on any error neither inventory
        changes. A SKU new to ``destination`` starts from zero there. Returns this
        inventory's new on-hand level.
        """
        on_hand = self.remove(sku, quantity)  # every check happens before anything changes
        destination.add(sku, quantity)
        return on_hand

    # -- reservations ----------------------------------------------------------------
''',
)
replace(
    "CHANGELOG.md",
    "# Changelog\n\n",
    "# Changelog\n\n## Unreleased\n- `Inventory.transfer()` moves available stock into another inventory.\n\n",
)
print("There is no Inventory.move() any more: the CHANGELOG says it was removed in 0.4.0 because it")
print("ignored reservations. transfer() therefore uses remove() (which validates the quantity and")
print("raises UnknownSku / InsufficientStock against available stock before changing anything) and")
print("then destination.add(), so a failed transfer leaves both inventories untouched.")
print("FINAL: done")
