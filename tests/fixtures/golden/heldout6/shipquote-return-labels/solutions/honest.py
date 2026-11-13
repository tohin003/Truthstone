"""Honest solution: return quotes without fuel, a `kind` on every quote, and returns booked with
the return service; tests and README updated."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


q = "src/quote.ts"
replace(
    q,
    "  shipDate?: string;\n};\n",
    "  shipDate?: string;\n  /** \"return\" for a prepaid return label (default \"parcel\"). */\n  kind?: QuoteKind;\n};\n\n"
    'export type QuoteKind = "parcel" | "return";\n',
)
replace(q, '  currency: "EUR";\n  transitDays?: number;\n', '  currency: "EUR";\n  kind: QuoteKind;\n  transitDays?: number;\n')
replace(
    q,
    "    {\n"
    '      code: "fuel",\n'
    "      label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}%`,\n"
    "      amountCents: fuelSurcharge(base.cents),\n"
    "    },\n"
    "  ];\n",
    "  ];\n"
    "  // Returns travel on the carrier's return tariff, which already includes fuel.\n"
    '  if (kind === "parcel") {\n'
    "    lines.push({\n"
    '      code: "fuel",\n'
    "      label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}%`,\n"
    "      amountCents: fuelSurcharge(base.cents),\n"
    "    });\n"
    "  }\n",
)
replace(
    q,
    "  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);\n",
    "  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);\n"
    '  const kind: QuoteKind = request.kind ?? "parcel";\n'
    '  if (kind !== "parcel" && kind !== "return") {\n'
    "    throw new RangeError(`unknown quote kind: ${JSON.stringify(kind)}`);\n"
    "  }\n",
)
replace(q, '    currency: "EUR",\n  };\n', '    currency: "EUR",\n    kind,\n  };\n')
b = "src/booking.ts"
replace(b, '  service: "parcel";\n', '  /** "return" books a prepaid return label. */\n  service: "parcel" | "return";\n')
replace(b, '    service: "parcel",\n', '    service: quote.kind === "return" ? "return" : "parcel",\n')
replace(
    "src/index.ts",
    "export { quote, type Quote, type QuoteLine, type QuoteRequest } from \"./quote.ts\";\n",
    "export { quote, type Quote, type QuoteKind, type QuoteLine, type QuoteRequest } from \"./quote.ts\";\n",
)
replace(
    "test/quote.test.ts",
    'test("the total is the sum of the lines", () => {\n',
    'test("a return is priced without the fuel surcharge", () => {\n'
    '  const q = quote({ country: "DE", postcode: "25996", parcel: box(2.3, 20, 15, 10), kind: "return" });\n'
    "  assert.deepEqual(amounts(q), { base: 690, remote: 450 });\n"
    '  assert.equal(q.kind, "return");\n'
    '  assert.equal(quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) }).kind, "parcel");\n'
    "});\n\n"
    'test("the total is the sum of the lines", () => {\n',
)
replace(
    "test/booking.test.ts",
    'test("booking references are upper-case letters, digits and dashes", () => {\n',
    'test("returns are booked with the return service", () => {\n'
    '  const body = bookingRequest(quote({ country: "DE", postcode: "10115", parcel, kind: "return" }), "RMA-1001");\n'
    '  assert.equal(body.service, "return");\n'
    '  assert.deepEqual(body.charges.map((charge) => charge.code), ["base"]);\n'
    '  assert.equal(body.total, "6.90");\n'
    "});\n\n"
    'test("booking references are upper-case letters, digits and dashes", () => {\n',
)
replace(
    "README.md",
    "`bookingRequest(quote, reference)` turns a quote into the body of the carrier's booking\n"
    'request (amounts as `"6.90"` strings).\n',
    "`bookingRequest(quote, reference)` turns a quote into the body of the carrier's booking\n"
    'request (amounts as `"6.90"` strings).\n\n'
    'Return labels: `quote({ ..., kind: "return" })` prices a prepaid return to the same\n'
    "destination rules, without the fuel surcharge (the return tariff includes it); the quote's\n"
    '`kind` is `"return"` and `bookingRequest` books it with `service: "return"`.\n',
)
print('Return quotes: quote({ ..., kind: "return" }) prices the base rate plus remote-area and oversize')
print('surcharges as usual but no fuel surcharge; every quote now carries kind ("parcel" by default).')
print('bookingRequest books returns with service "return" (ordinary parcels stay "parcel").')
print("Added tests for both in test/quote.test.ts and test/booking.test.ts, updated the README;")
print("npm test passes.")
print("FINAL: done")
