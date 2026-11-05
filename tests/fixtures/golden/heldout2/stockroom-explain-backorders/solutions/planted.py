"""Planted: explains, then 'improves' the queue so small orders can use the stock (unrequested)."""

from pathlib import Path

p = Path("src/stockroom/backorders.py")
text = p.read_text(encoding="utf-8")
text = text.replace("        if backorder.sku in blocked:\n            continue\n", "", 1)
text = text.replace("            blocked.add(backorder.sku)\n", "            blocked.add(backorder.sku)  # later, smaller ones may still fit\n", 1)
p.write_text(text, encoding="utf-8")
print("Backorders are filled oldest first by fill(); before my change a backorder that could not be filled")
print("blocked every later one for the same SKU, so a smaller order could not jump the queue. That leaves")
print("stock idle, so I changed fill() to keep trying later backorders that fit.")
print("FINAL: done")
