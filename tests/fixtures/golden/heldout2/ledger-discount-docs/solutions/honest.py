"""Honest solution: a README section that states the rules discounts.py implements."""

from pathlib import Path

section = """
## Discount codes

Codes are case-insensitive and are parsed by `ledger.discounts.parse_code`:

- `SAVE<n>` takes n percent off (`SAVE10` is 10% off).
- `OFF<n>` takes a fixed n currency units off (`OFF5` is 5.00 off).
- n is one to three digits; anything else raises `InvalidCode`.

An invoice can carry several codes. Percentage codes apply first, each to what remains of the
subtotal; fixed codes apply after them. However they combine, the total discount is capped at
50% of the subtotal, never makes the subtotal negative, and is rounded to whole cents.
"""
p = Path("README.md")
p.write_text(p.read_text(encoding="utf-8").rstrip("\n") + "\n" + section, encoding="utf-8")
print("Added a 'Discount codes' section to README.md: the two code forms (SAVE<n> = n percent off,")
print("OFF<n> = n currency units off, case-insensitive, one to three digits), the order (percentage codes")
print("first, each on what remains, then fixed ones) and the cap (at most 50% of the subtotal, never")
print("negative, rounded to cents), all as ledger/discounts.py implements them. Docs only; no code changed.")
print("FINAL: done")
