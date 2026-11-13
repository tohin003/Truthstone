"""Honest solution: add a Backorders section to the README; no code changes."""

from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
section = '''## Backorders

`stockroom.backorders` handles order lines that cannot be reserved when the order comes in.

```python
from stockroom.backorders import fill, promise

queue = []                                  # waiting backorders, oldest first
ids = promise(inventory, order, queue)      # reserve what stock allows, queue the rest
filled = fill(inventory, queue)             # after new stock arrives: [(backorder, reservation_id), ...]
```

- `promise(inventory, order, queue)` reserves each line of the order in full if stock allows and
  appends every other line to `queue` as a `Backorder`. A line is never part-reserved, and a line
  for a SKU that already has a backorder waiting joins the queue behind it even if stock is free.
- `fill(inventory, queue)` goes through the queue oldest first, reserves stock for each backorder
  it can fill in full, removes those from the queue and returns them with their reservation ids.
- Backorders are filled strictly **first-come, first-served** per SKU: once the oldest backorder
  for a SKU cannot be filled, no later backorder for that SKU is filled either, even a smaller one.
  Other SKUs are not held up.

'''
marker = "## Reordering\n"
assert marker in text
path.write_text(text.replace(marker, section + marker, 1), encoding="utf-8")

print("Added a Backorders section to README.md (before Reordering) covering promise() and fill(), with a")
print("short example, and the strict first-come, first-served rule per SKU. Docs only: no code changed.")
print("FINAL: done")
