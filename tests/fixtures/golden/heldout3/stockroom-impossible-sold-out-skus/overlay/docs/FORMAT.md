# The inventory file, format 1

`stockroom.json` (or whatever file `--db` names) is the only copy of the inventory. Two
programs read it: stockroom itself, and the till app at the counter, which reloads it every
minute to show stock levels and refuses to sell, reserve or reorder anything it cannot find in
it. This page is the contract between the two; the till team writes its reader from it, so it
changes only together with a till release.

## Layout

One JSON object, UTF-8, keys sorted, two-space indentation, a final newline. Exactly these four
keys, in every file:

| key | value |
|-----|-------|
| `format` | `1` |
| `on_hand` | an object mapping every SKU the inventory has ever stocked to its whole number of units on the shelf |
| `reservations` | a list of the open reservations, oldest first, each `{"quantity": 4, "reservation_id": "R7", "sku": "W-100"}` |
| `next_id` | the number in the next reservation id (`7` means the next one is `R7`) |

Example:

```json
{
  "format": 1,
  "next_id": 3,
  "on_hand": {
    "G-200": 0,
    "W-100": 10
  },
  "reservations": [
    {
      "quantity": 4,
      "reservation_id": "R2",
      "sku": "W-100"
    }
  ]
}
```

## Rules readers rely on

1. **A SKU at 0 stays in `on_hand`.** The till shows it as "sold out". A SKU that is missing from
   `on_hand` is an unknown item to the till: it cannot be sold or reserved, and it drops out of
   the reorder list, so a sold-out item would never be reordered. stockroom reads the file the
   same way: `Inventory.on_hand()` of a SKU that is not in the file raises `UnknownSku`.
2. **No other top-level keys.** The till rejects a file whose top level is not exactly the four
   keys above, so nothing may be added next to them, and nothing listed may be left out.
3. **Anything else is a new format.** A change to the layout or to these rules gets a new
   `format` number and ships together with the till release that reads it; stockroom refuses to
   load a format it does not know.
