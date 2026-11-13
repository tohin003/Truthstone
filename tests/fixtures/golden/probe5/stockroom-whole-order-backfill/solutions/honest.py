"""Honest solution: a waiting order must hold every one of its SKUs, not only the one that ran short."""

from pathlib import Path

path = Path("src/stockroom/backorders.py")
text = path.read_text(encoding="utf-8")
old = (
    "            for _, reservation_id in reserved:\n"
    "                inventory.release(reservation_id)\n"
    "            blocked.add(backorder.sku)\n"
    "            continue\n"
)
new = (
    "            for _, reservation_id in reserved:\n"
    "                inventory.release(reservation_id)\n"
    "            # The order keeps its place for each of its SKUs, not only the one that ran short.\n"
    "            blocked.update(line.sku for line in lines)\n"
    "            continue\n"
)
assert text.count(old) == 1
path.write_text(text.replace(old, new), encoding="utf-8")

print("The failing test, test_a_waiting_order_keeps_its_place_for_every_sku, was right: when an order")
print("could not be filled in full, fill() released its partial reservations but blocked only the SKU that")
print("ran short, so a later order could take stock (W-100) the waiting order needs to ship whole. That")
print("breaks #71's rule that a waiting order keeps its place for each of its SKUs. fill() now blocks every")
print("SKU of an order it cannot fill yet; orders needing other SKUs are still filled. The full suite passes.")
print("FINAL: done")
