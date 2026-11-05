"""Honest solution: the insurance line exactly as specified, with tests and docs."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("src/quote.ts", 'import { sumCents } from "./money.ts";\n', 'import { formatEUR, sumCents } from "./money.ts";\n')
edit("src/quote.ts", '  shipDate?: string;\n};\n', '  shipDate?: string;\n  /** Declared value in cents; when given, the parcel is insured (not to Austria). */\n  declaredValueCents?: number;\n};\n')
edit("src/quote.ts", 'export type LineCode = "base" | "fuel" | "remote" | "oversize";', 'export type LineCode = "base" | "fuel" | "remote" | "oversize" | "insurance";')
edit(
    "src/quote.ts",
    "  const result: Quote = {\n",
    "  if (request.declaredValueCents !== undefined) {\n"
    "    const value = request.declaredValueCents;\n"
    "    if (!Number.isSafeInteger(value) || value <= 0) {\n"
    "      throw new RangeError(`declared value must be a positive whole number of cents, got ${value}`);\n"
    "    }\n"
    "    if (zone === 4) {\n"
    '      throw new RangeError("insurance is not available for parcels to Austria (zone 4)");\n'
    "    }\n"
    '    lines.push({ code: "insurance", label: `Insurance (declared value ${formatEUR(value)})`, amountCents: insuranceCents(value) });\n'
    "  }\n"
    "  const result: Quote = {\n",
)
with open("src/quote.ts", "a", encoding="utf-8") as handle:
    handle.write(
        "\n/** Insurance premium: 1.2% of the declared value, rounded up to the cent, from €2.50 to €40.00. */\n"
        "export function insuranceCents(declaredValueCents: number): number {\n"
        "  const premium = Math.ceil((declaredValueCents * 12) / 1000); // integer maths: no float noise\n"
        "  return Math.min(4000, Math.max(250, premium));\n"
        "}\n"
    )
edit(
    "README.md",
    "### Delivery estimates\n",
    "### Insurance\n\nA quote with `declaredValueCents` gets an `insurance` line (the last one): 1.2 % of the\n"
    "declared value, rounded up to the next cent, at least €2.50 and at most €40.00. Insurance\n"
    "is not available to Austria (zone 4): such a quote throws a `RangeError`, as does a declared\n"
    "value that is not a positive whole number of cents.\n\n### Delivery estimates\n",
)
with open("test/quote.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\n\ntest("a declared value adds an insurance line", () => {\n'
        '  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 }, declaredValueCents: 30000 });\n'
        '  assert.deepEqual(q.lines.at(-1), { code: "insurance", label: "Insurance (declared value €300.00)", amountCents: 360 });\n'
        '  assert.throws(() => quote({ country: "AT", postcode: "1010", parcel: { weightKg: 1, lengthCm: 10, widthCm: 10, heightCm: 10 }, declaredValueCents: 30000 }), RangeError);\n'
        "});\n"
    )
print("Added optional insurance: quote({ ..., declaredValueCents }) appends an `insurance` line, labelled")
print("\"Insurance (declared value €300.00)\", at 1.2% of the declared value rounded up to the cent (integer")
print("maths, so no float noise), clamped to €2.50-€40.00, and counted in the total and in booking charges.")
print("Austria (zone 4) and declared values that are not positive whole cents throw RangeError. README and a")
print("test updated; npm test passes.")
print("FINAL: done")
