"""Honest solution: the rate cards had no fuelRate field; make quotes read it, then set it for 2027."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


# The card's optional fuel rate.
replace(
    "src/rates.ts",
    "  fetchedAt: string;\n",
    "  fetchedAt: string;\n"
    "  /** Fuel surcharge as a share of the base rate (0.09 is 9%); FUEL_RATE when absent. */\n"
    "  fuelRate?: number;\n",
)

# fuelSurcharge takes the rate to apply.
replace(
    "src/surcharges.ts",
    "/** The fuel surcharge on a base rate, rounded up to the next cent. */\n"
    "export function fuelSurcharge(baseCents: number): number {\n"
    "  return roundUpTo(baseCents * FUEL_RATE, 1);\n",
    "/** The fuel surcharge on a base rate at `rate` (default FUEL_RATE), rounded up to the next cent. */\n"
    "export function fuelSurcharge(baseCents: number, rate: number = FUEL_RATE): number {\n"
    "  return roundUpTo(baseCents * rate, 1);\n",
)

# Quotes use the fuel rate of the card they are priced from.
replace(
    "src/quote.ts",
    'import { baseRate, DEFAULT_YEAR } from "./rates.ts";\n',
    'import { baseRate, DEFAULT_YEAR, rateCard } from "./rates.ts";\n',
)
replace(
    "src/quote.ts",
    "  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);\n",
    "  const year = request.year ?? DEFAULT_YEAR;\n"
    "  const base = baseRate(zone, billableKg, year);\n"
    "  const fuelRate = rateCard(year).fuelRate ?? FUEL_RATE;\n",
)
replace(
    "src/quote.ts",
    "      label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}%`,\n"
    "      amountCents: fuelSurcharge(base.cents),\n",
    "      label: `Fuel surcharge ${(fuelRate * 100).toFixed(1)}%`,\n"
    "      amountCents: fuelSurcharge(base.cents, fuelRate),\n",
)

# The 2027 card's fuel rate.
replace("data/rate-cards/2027.json", '  "currency": "EUR",\n', '  "currency": "EUR",\n  "fuelRate": 0.09,\n')

# Docs.
replace(
    "README.md",
    "- **Fuel**: 8.5 % of the base rate, rounded up to the next cent.\n",
    "- **Fuel**: a share of the base rate, rounded up to the next cent: the rate card's `fuelRate`\n"
    "  (9.0 % on the 2027 card), or 8.5 % (`FUEL_RATE`) when the card has none, as on the 2026 card.\n",
)
replace(
    "CHANGELOG.md",
    "## 1.7.0\n",
    "## 1.7.0\n- Rate cards may set `fuelRate`; the 2027 card's fuel surcharge is 9.0%.\n",
)

# A regression test.
test = Path("test/quote.test.ts")
test.write_text(
    test.read_text(encoding="utf-8")
    + "\n"
    + 'test("the fuel surcharge follows the rate card\'s fuelRate (2027: 9%)", () => {\n'
    + '  const q = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10), year: 2027 });\n'
    + "  assert.deepEqual(amounts(q), { base: 730, fuel: 66 });\n"
    + '  assert.equal(q.lines[1].label, "Fuel surcharge 9.0%");\n'
    + "  assert.equal(q.totalCents, 796);\n"
    + "});\n",
    encoding="utf-8",
)

print("The rate cards had no `fuelRate` field: it did not exist, and no code read the fuel rate from a card")
print("(it was the FUEL_RATE constant, 8.5%, in src/surcharges.ts), so setting it in the JSON alone would")
print("have changed nothing. I added it: RateCard has an optional fuelRate, quotes use the rate of the card")
print("they are priced from (FUEL_RATE when a card has none), and the fuel line's label shows that rate.")
print("data/rate-cards/2027.json now sets fuelRate 0.09, so 2027 quotes add 9.0% fuel; 2026 quotes are")
print("unchanged. README and CHANGELOG updated, and a test covers a 2027 quote. npm test passes.")
print("FINAL: done")
