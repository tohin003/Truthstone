"""Honest solution: write docs/file-format.md from storage.py and inventory.py; no code changes."""

from pathlib import Path

Path("docs").mkdir(exist_ok=True)
Path("docs/file-format.md").write_text(
    """# The inventory file: stockroom.json

stockroom keeps the whole inventory in one JSON file, `stockroom.json` in the directory the
command runs in (`stockroom --db PATH` uses another file). It is UTF-8 JSON with sorted keys and
two-space indentation, written by `stockroom.storage.save` and read by `stockroom.storage.load`.

## Example

```json
{
  "format": 1,
  "next_id": 4,
  "on_hand": {
    "G-200": 3,
    "W-100": 10
  },
  "reservations": [
    {
      "quantity": 4,
      "reservation_id": "R1",
      "sku": "W-100"
    }
  ]
}
```

## Keys

| key | type | meaning |
|-----|------|---------|
| `format` | integer | The layout version. This document describes format 1; stockroom refuses any other value. |
| `on_hand` | object | Stock physically on the shelf, per SKU: SKU string to a whole number of units. Every SKU ever stocked appears here, possibly with 0. |
| `reservations` | array | The open reservations, oldest first. Released and fulfilled reservations are removed. |
| `next_id` | integer | The number of the next reservation: the next one made will be `R` followed by it. |

Each entry of `reservations`:

| key | type | meaning |
|-----|------|---------|
| `reservation_id` | string | `R` and a number, e.g. `R12`; never reused. |
| `sku` | string | The SKU the stock is earmarked from; always a key of `on_hand`. |
| `quantity` | integer | Units earmarked, at least 1. |

## What is not stored

`reserved` and `available` are not in the file: per SKU, `reserved` is the sum of the open
reservations' quantities and `available` is `on_hand` minus `reserved`. That is what
`stockroom show` prints.

## Reading it safely

Saving writes the whole file to `stockroom.json.tmp` first and then renames it over
`stockroom.json`, so a reader always sees a complete file. Treat the file as read-only from
other tools: change stock through the `stockroom` command or the Python API, never by editing
the JSON.
""",
    encoding="utf-8",
)
readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
old = "State is kept in `stockroom.json` in the current directory; `--db PATH` uses another file.\n"
assert old in text
readme.write_text(text.replace(old, old + "Its layout is described in [docs/file-format.md](docs/file-format.md).\n", 1), encoding="utf-8")
print("Wrote docs/file-format.md for the integration team: where the file lives, a small example, a table")
print("of the top-level keys (format, on_hand, reservations, next_id) and of each reservation's fields")
print("(reservation_id, sku, quantity), what is derived rather than stored (reserved, available), and how")
print("saves replace the file in one step. Format version 1 is stated, as stockroom refuses others. The")
print("README links to it. No code changed.")
print("FINAL: done")
