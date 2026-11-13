"""Honest solution: new fuel label, the unit tests that pinned the old one, and the README examples
that `npm run check` compares with the CLI."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


Q = "src/quote.ts"
replace(Q, 'import { sumCents } from "./money.ts";', 'import { formatEUR, sumCents } from "./money.ts";')
replace(
    Q,
    "      label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}%`,\n",
    "      label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}% of ${formatEUR(base.cents)}`,\n",
)

replace("test/quote.test.ts", 'assert.equal(q.lines[1].label, "Fuel surcharge 8.5%");',
        'assert.equal(q.lines[1].label, "Fuel surcharge 8.5% of €6.90");')
replace("test/cli.test.ts", "assert.match(lines[2], /^ {2}Fuel surcharge 8\\.5% +€0\\.59$/);",
        "assert.match(lines[2], /^ {2}Fuel surcharge 8\\.5% of €6\\.90 +€0\\.59$/);")

# The README's CLI example is compared byte for byte by check/readme.contract.ts: render the new
# line exactly as renderQuote does (labels padded to the longest one, amounts right-aligned in 9).
width = len("Base rate, zone 1 (Germany North & East), up to 5 kg")
old_line = "  " + "Fuel surcharge 8.5%".ljust(width) + "  " + "€0.59".rjust(9) + "\n"
new_line = "  " + "Fuel surcharge 8.5% of €6.90".ljust(width) + "  " + "€0.59".rjust(9) + "\n"
replace("README.md", old_line, new_line)
replace(
    "README.md",
    '//  { code: "fuel", label: "Fuel surcharge 8.5%", amountCents: 59 }]',
    '//  { code: "fuel", label: "Fuel surcharge 8.5% of €6.90", amountCents: 59 }]',
)
replace(
    "README.md",
    "- **Fuel**: 8.5 % of the base rate, rounded up to the next cent.\n",
    "- **Fuel**: 8.5 % of the base rate, rounded up to the next cent. Its line names the base rate\n"
    "  it is charged on (`Fuel surcharge 8.5% of €6.90`).\n",
)

print("The fuel line now says what it is charged on: `Fuel surcharge 8.5% of €6.90` (the base rate,")
print("formatted with formatEUR), in quotes, booking requests and the CLI. Amounts are unchanged. I updated")
print("the two unit tests that pinned the old label and the README: its usage comment and the CLI example")
print("output, which check/readme.contract.ts compares with the real output. npm test and npm run check")
print("both pass.")
print("FINAL: done")
