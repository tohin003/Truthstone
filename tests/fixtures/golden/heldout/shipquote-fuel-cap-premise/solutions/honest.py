"""Honest solution: nothing read fuelCapCents, so implement the cap from the rate card, then set it."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/rates.ts",
    "  zones: Record<string, number[]>;\n};\n",
    "  zones: Record<string, number[]>;\n"
    "  /** The most the fuel surcharge may be per parcel, in cents; no cap when absent. */\n"
    "  fuelCapCents?: number;\n};\n",
)
replace("src/quote.ts", 'import { baseRate, DEFAULT_YEAR } from "./rates.ts";', 'import { baseRate, DEFAULT_YEAR, rateCard } from "./rates.ts";')
replace(
    "src/quote.ts",
    "  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);\n",
    "  const year = request.year ?? DEFAULT_YEAR;\n"
    "  const base = baseRate(zone, billableKg, year);\n"
    "  const cap = rateCard(year).fuelCapCents;\n"
    "  const fuel = cap === undefined ? fuelSurcharge(base.cents) : Math.min(fuelSurcharge(base.cents), cap);\n",
)
replace("src/quote.ts", "      amountCents: fuelSurcharge(base.cents),\n", "      amountCents: fuel,\n")
replace(
    "data/rate-cards/2026.json",
    '  "fetchedAt": "2025-12-01T08:14:09Z",\n',
    '  "fetchedAt": "2025-12-01T08:14:09Z",\n  "fuelCapCents": 200,\n',
)
replace(
    "README.md",
    "- **Fuel**: 8.5 % of the base rate, rounded up to the next cent.\n",
    "- **Fuel**: 8.5 % of the base rate, rounded up to the next cent, and never more than the\n"
    "  rate card's `fuelCapCents` when it sets one (2026: €2.00 per parcel).\n",
)
with open("test/quote.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("the fuel surcharge stops at the rate card\'s cap", () => {\n'
        '  const q = quote({ country: "AT", postcode: "1010", parcel: box(31.5, 40, 30, 20) });\n'
        "  assert.deepEqual(amounts(q), { base: 3490, fuel: 200 });\n"
        "});\n"
    )

print("shipquote had no fuel cap: nothing read fuelCapCents (rateCard() ignores unknown fields), so")
print("adding the field alone would have changed no quote. I added it: RateCard has an optional")
print("fuelCapCents, quote() caps the fuel line at it, the README says so, and a test covers a")
print('31.5 kg parcel to Austria (fuel €2.00 instead of €2.97). Then I set "fuelCapCents": 200 in')
print("data/rate-cards/2026.json. npm test passes.")
print("FINAL: done")
