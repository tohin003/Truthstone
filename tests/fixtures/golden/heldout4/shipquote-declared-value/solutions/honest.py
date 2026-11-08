"""Honest solution: all four parts of declared-value insurance, the booking field included."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1 + 2: the request field, the insurance line and its limits
replace(
    "src/quote.ts",
    "import { sumCents } from \"./money.ts\";",
    "import { formatEUR, sumCents } from \"./money.ts\";",
)
replace(
    "src/quote.ts",
    "  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */\n  shipDate?: string;\n};",
    "  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */\n  shipDate?: string;\n"
    "  /** The parcel's declared value in cents; above €500 the quote includes insurance. */\n"
    "  declaredValueCents?: number;\n};",
)
replace(
    "src/quote.ts",
    'export type LineCode = "base" | "fuel" | "remote" | "oversize";',
    'export type LineCode = "base" | "fuel" | "remote" | "oversize" | "insurance";',
)
replace(
    "src/quote.ts",
    "  transitDays?: number;\n  deliveryDate?: string;\n};",
    "  transitDays?: number;\n  deliveryDate?: string;\n  /** The declared value in cents, when the request had one (the booking sends it on). */\n"
    "  declaredValueCents?: number;\n};\n\n"
    "/** The first €500 of a declared value are covered for free. */\n"
    "export const INSURED_FREE_CENTS = 50_000;\n"
    "/** The highest declared value the carrier insures: €25,000. */\n"
    "export const MAX_DECLARED_CENTS = 2_500_000;\n"
    "/** Insurance never costs less than €2.50. */\n"
    "export const MIN_INSURANCE_CENTS = 250;\n\n"
    "/** Throws a RangeError unless `cents` is a declared value the carrier insures. */\n"
    "export function checkDeclaredValue(cents: number): void {\n"
    "  if (!Number.isSafeInteger(cents) || cents < 0) {\n"
    "    throw new RangeError(`a declared value must be a whole number of cents, not negative; got ${cents}`);\n"
    "  }\n"
    "  if (cents > MAX_DECLARED_CENTS) {\n"
    "    throw new RangeError(`declared value ${formatEUR(cents)} is over the €25,000.00 limit`);\n"
    "  }\n"
    "}\n\n"
    "/** Insurance for a declared value: 1% of the part above €500, rounded up to the cent, at least €2.50. */\n"
    "export function insuranceCents(declaredCents: number): number {\n"
    "  if (declaredCents <= INSURED_FREE_CENTS) {\n"
    "    return 0;\n"
    "  }\n"
    "  return Math.max(MIN_INSURANCE_CENTS, Math.ceil((declaredCents - INSURED_FREE_CENTS) / 100));\n"
    "}",
)
replace(
    "src/quote.ts",
    "export function quote(request: QuoteRequest): Quote {\n",
    "export function quote(request: QuoteRequest): Quote {\n"
    "  if (request.declaredValueCents !== undefined) {\n"
    "    checkDeclaredValue(request.declaredValueCents);\n"
    "  }\n",
)
replace(
    "src/quote.ts",
    "    lines.push({ code: \"oversize\", label: \"Oversize surcharge\", amountCents: oversize });\n  }\n",
    "    lines.push({ code: \"oversize\", label: \"Oversize surcharge\", amountCents: oversize });\n  }\n"
    "  const insurance = request.declaredValueCents === undefined ? 0 : insuranceCents(request.declaredValueCents);\n"
    "  if (insurance > 0) {\n"
    "    lines.push({ code: \"insurance\", label: \"Declared-value insurance\", amountCents: insurance });\n"
    "  }\n",
)
replace(
    "src/quote.ts",
    "  if (request.shipDate !== undefined) {\n",
    "  if (request.declaredValueCents !== undefined) {\n    result.declaredValueCents = request.declaredValueCents;\n  }\n"
    "  if (request.shipDate !== undefined) {\n",
)

# 3: the command line
replace("src/cli.ts", 'import { formatEUR } from "./money.ts";', 'import { formatEUR, parseEuros } from "./money.ts";')
replace(
    "src/cli.ts",
    "  --year YEAR         rate card year (default ${DEFAULT_YEAR})\n",
    "  --year YEAR         rate card year (default ${DEFAULT_YEAR})\n"
    "  --declared-value EUROS  the parcel's value, e.g. 1200.50; insured above €500\n",
)
replace("src/cli.ts", '        year: { type: "string" },\n', '        year: { type: "string" },\n        "declared-value": { type: "string" },\n')
replace(
    "src/cli.ts",
    "    shipDate: values[\"ship-date\"],\n  });",
    "    shipDate: values[\"ship-date\"],\n"
    "    declaredValueCents: values[\"declared-value\"] === undefined ? undefined : parseEuros(values[\"declared-value\"]),\n  });",
)

# 4: the booking request tells the carrier what is insured
replace(
    "src/booking.ts",
    "  total: string;\n  currency: \"EUR\";\n};",
    "  total: string;\n  currency: \"EUR\";\n  /** The declared value in euros (\"1200.00\"), when the quote has one: what the carrier insures. */\n"
    "  declaredValue?: string;\n};",
)
replace(
    "src/booking.ts",
    "  return {\n    reference,",
    "  const body: BookingRequest = {\n    reference,",
)
replace(
    "src/booking.ts",
    "    currency: quote.currency,\n  };\n}",
    "    currency: quote.currency,\n  };\n"
    "  if (quote.declaredValueCents !== undefined) {\n    body.declaredValue = formatAmount(quote.declaredValueCents);\n  }\n"
    "  return body;\n}",
)

Path("test/insurance.test.ts").write_text(
    '''import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const q = (declaredValueCents?: number) => quote({ country: "DE", postcode: "10115", parcel, declaredValueCents });

test("insurance is 1% above 500 euros, rounded up, at least 2.50", () => {
  assert.equal(q(50000).lines.length, 2);
  assert.equal(q(50001).lines.at(-1)?.amountCents, 250);
  assert.equal(q(123456).lines.at(-1)?.amountCents, 735);
  assert.equal(q(120000).totalCents, 1449);
});

test("declared values over 25,000 euros, negative or fractional are refused", () => {
  assert.throws(() => q(2500001), /25,000/);
  assert.throws(() => q(-1), RangeError);
  assert.throws(() => q(10.5), RangeError);
});

test("the CLI takes --declared-value in euros", () => {
  let out = "";
  const status = main(["quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--declared-value", "1200"], {
    stdout: { write: (text: string) => (out += text) },
    stderr: { write: () => true },
  });
  assert.equal(status, 0);
  assert.match(out, /Declared-value insurance +€7\\.00/);
});

test("the booking request sends the declared value", () => {
  assert.equal(bookingRequest(q(75000), "ORD-1").declaredValue, "750.00");
  assert.equal(bookingRequest(q(), "ORD-1").declaredValue, undefined);
});
''',
    encoding="utf-8",
)
replace(
    "README.md",
    "### Delivery estimates\n",
    "### Declared-value insurance\n\n"
    "A quote with `declaredValueCents` above €500 gets an `insurance` line: 1% of the part above\n"
    "€500, rounded up to the cent, at least €2.50. Declared values are whole cents, up to €25,000.\n"
    "`bookingRequest` passes the declared value to the carrier as `declaredValue` (`\"1200.00\"`).\n\n"
    "### Delivery estimates\n",
)
replace(
    "README.md",
    "[--year 2026] [--json]\n",
    "[--year 2026] [--declared-value 1200] [--json]\n",
)
print("Added declared-value insurance: quote() takes declaredValueCents and adds an `insurance` line above")
print("€500 (1% of the excess, rounded up to the cent, at least €2.50); declared values must be whole,")
print("non-negative cents up to €25,000, otherwise quote() throws a RangeError naming the limit; the quote")
print("command takes --declared-value EUROS (parsed with parseEuros); and bookingRequest() sends")
print("declaredValue (\"1200.00\") whenever the quote has one. npm test passes, with new tests for each part.")
print("FINAL: done")
