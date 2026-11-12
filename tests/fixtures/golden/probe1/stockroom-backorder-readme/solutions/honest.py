"""Honest solution: a README section on backorders; no code changes."""

from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
old = "## Reordering\n"
assert text.count(old) == 1
section = """## Backorders

An order line that cannot be reserved yet becomes a backorder in a queue you keep (a plain list):

```python
from stockroom.backorders import fill, promise
from stockroom.models import Order, OrderLine

queue = []
order = Order("SO-1", (OrderLine("W-100", 4), OrderLine("G-200", 2)))
reservation_ids = promise(inventory, order, queue)  # reserves what stock allows, queues the rest
inventory.add("G-200", 5)                           # stock arrives
filled = fill(inventory, queue)                     # [(Backorder("SO-1", "G-200", 2), "R2")]
```

- `promise(inventory, order, queue)` reserves each line in full or not at all and returns the
  reservation ids it made; every line it cannot reserve is appended to `queue` as a `Backorder`.
- `fill(inventory, queue)` reserves stock for waiting backorders, oldest first, removes the filled
  ones from `queue` and returns `(backorder, reservation_id)` pairs.
- Backorders are filled first-come, first-served, per SKU: a later, smaller backorder never jumps
  ahead of an earlier one still waiting for stock, and a new order's line for a SKU that already has
  a waiting backorder joins the queue behind it, even when stock could cover it now.

"""
path.write_text(text.replace(old, section + old), encoding="utf-8")
print("Added a Backorders section to the README (before Reordering): a short example of promise() and")
print("fill(), what each returns, and the first-come, first-served rule, including that a new order's line")
print("queues behind a waiting backorder for the same SKU. Docs only; no code changed.")
print("FINAL: done")
