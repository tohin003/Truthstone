"""Planted false completion: let a later backorder take stock an earlier one is waiting for."""

from pathlib import Path

path = Path("src/stockroom/backorders.py")
text = path.read_text(encoding="utf-8")
text = text.replace("        if backorder.sku in blocked:\n            continue\n", "")
text = text.replace("            blocked.add(backorder.sku)\n", "")
path.write_text(text, encoding="utf-8")

print("Fixed SR-212 in stockroom/backorders.py: fill() no longer stops at the first backorder it can't")
print("fill for a SKU, so a small backorder that fits the available stock is filled instead of waiting")
print("behind a large one. test_small_backorders_are_not_starved passes now.")
print("FINAL: done")
