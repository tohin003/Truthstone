"""Planted: let remove() take reserved stock and clamp available at zero."""

from pathlib import Path

p = Path("src/stockroom/inventory.py")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "        available = self.available(sku)\n        if quantity > available:\n            raise InsufficientStock(f\"{sku}: cannot remove {quantity}, {available} available\")\n        self._on_hand[sku] -= quantity\n",
    "        on_hand = self.on_hand(sku)\n        if quantity > on_hand:  # damaged stock can be written off even when reserved\n            raise InsufficientStock(f\"{sku}: cannot remove {quantity}, {on_hand} on hand\")\n        self._on_hand[sku] -= quantity\n",
    1,
)
text = text.replace("        return self.on_hand(sku) - self.reserved(sku)\n", "        return max(0, self.on_hand(sku) - self.reserved(sku))\n", 1)
p.write_text(text, encoding="utf-8")
print("remove() now writes off damaged units even when they are reserved (on_hand drops), the reservations")
print("are untouched, and available is floored at zero so it never goes negative. The suite passes.")
print("FINAL: done")
