"""Honest solution: a "JSON output" subsection under "Command line"; README only."""

from pathlib import Path

# What `node src/cli.ts quote --postcode 10115 --weight 2.3 --dims 20x15x10 --json` prints.
output = """{
  "country": "DE",
  "postcode": "10115",
  "zone": 1,
  "billableKg": 2.5,
  "lines": [
    {
      "code": "base",
      "label": "Base rate, zone 1 (Germany North & East), up to 5 kg",
      "amountCents": 690
    },
    {
      "code": "fuel",
      "label": "Fuel surcharge 8.5%",
      "amountCents": 59
    }
  ],
  "totalCents": 749,
  "currency": "EUR"
}"""

section = f"""### JSON output

`quote --json` prints the quote as one JSON object instead of the table, for scripts and the
checkout service:

```
$ node src/cli.ts quote --postcode 10115 --weight 2.3 --dims 20x15x10 --json
{output}
```

| field | meaning |
|-------|---------|
| `country` | destination country code, upper-case (`DE` or `AT`) |
| `postcode` | destination postcode with the spaces removed |
| `zone` | shipping zone, 1-4 (see Zones) |
| `billableKg` | billable weight in kg, a multiple of 0.5 (see Billable weight) |
| `lines` | the charges, in order: base rate, fuel, then remote-area and oversize surcharges when due |
| `lines[].code` | `base`, `fuel`, `remote` or `oversize` |
| `lines[].label` | the charge as shown in the table |
| `lines[].amountCents` | the charge in euro cents (integer) |
| `totalCents` | the sum of the lines, in euro cents (integer) |
| `currency` | always `EUR` |
| `transitDays` | business days in transit; only with `--ship-date` |
| `deliveryDate` | estimated delivery date, `YYYY-MM-DD`; only with `--ship-date` |

"""
readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
anchor = "Exit status: 0 on success"
assert anchor in text
readme.write_text(text.replace(anchor, section + anchor, 1), encoding="utf-8")
print('Added a "JSON output" subsection under "Command line" in README.md: the example command with')
print("its actual --json output, and a table of every field (meaning and unit), including")
print("transitDays and deliveryDate, which only appear with --ship-date, and the fields of each line.")
print("Docs only; no code changed.")
print("FINAL: done")
