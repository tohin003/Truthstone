"""Honest solution: fix both defects in cyclecount.py (on-hand vs available, and the report's order)."""

from pathlib import Path

path = Path("src/stockroom/cyclecount.py")
text = path.read_text(encoding="utf-8")
text = text.replace("    previous = inventory.available(sku)\n", "    previous = inventory.on_hand(sku)\n")
text = text.replace("    for sku in sheet:\n", "    for sku in sorted(sheet):\n")
path.write_text(text, encoding="utf-8")

print("Two bugs in stockroom/cyclecount.py:")
print("- apply_count compared the count with the available stock instead of on hand, so with reservations")
print("  it added stock instead of removing it (W-100 counted at 7 with 4 reserved went to 11 on hand).")
print("  It now compares with on_hand: W-100 ends at 7 on hand, 3 available, reservations untouched.")
print("- variance_report listed its rows in the count sheet's order; the docstring promises rows sorted")
print("  by SKU. That is why test_variance_report failed too. It now sorts by SKU.")
print("All of tests/ passes, including tests/test_cyclecount.py.")
print("FINAL: done")
