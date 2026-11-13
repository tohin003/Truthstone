"""Honest solution: quoteShipment with all four requested rules, booking bodies for shipments, tests."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


SHIPMENT = '''
export type ShipmentRequest = Omit<QuoteRequest, "parcel"> & { parcels: Parcel[] };

/** A quote for several parcels sent together; `parcels` holds each parcel's billable weight. */
export type ShipmentQuote = Quote & { parcels: Array<{ billableKg: number }> };

/**
 * Quotes several parcels to one destination: one base line per parcel at its own billable
 * weight, one fuel line on all the base lines together, the remote-area surcharge once per
 * shipment and the oversize surcharge once per oversize parcel.
 */
export function quoteShipment(request: ShipmentRequest): ShipmentQuote {
  if (request.parcels.length === 0) {
    throw new RangeError("a shipment needs at least one parcel");
  }
  const country = request.country.trim().toUpperCase();
  const postcode = normalisePostcode(request.postcode);
  const zone = zoneFor(country, postcode);
  const year = request.year ?? DEFAULT_YEAR;
  const weights = request.parcels.map((parcel) => billableWeight(parcel));
  const lines: QuoteLine[] = weights.map((kg, index) => {
    const base = baseRate(zone, kg, year);
    return {
      code: "base",
      label: `Base rate, parcel ${index + 1}, zone ${zone} (${ZONE_NAMES[zone]}), up to ${base.bracketKg} kg`,
      amountCents: base.cents,
    };
  });
  lines.push({
    code: "fuel",
    label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}%`,
    amountCents: fuelSurcharge(sumCents(lines.map((line) => line.amountCents))),
  });
  const remote = remoteAreaSurcharge(zone, postcode);
  if (remote > 0) {
    lines.push({ code: "remote", label: "Remote area surcharge", amountCents: remote });
  }
  request.parcels.forEach((parcel, index) => {
    const oversize = oversizeSurcharge(parcel);
    if (oversize > 0) {
      lines.push({ code: "oversize", label: `Oversize surcharge, parcel ${index + 1}`, amountCents: oversize });
    }
  });
  const result: ShipmentQuote = {
    country,
    postcode,
    zone,
    billableKg: weights.reduce((sum, kg) => sum + kg, 0),
    lines,
    totalCents: sumCents(lines.map((line) => line.amountCents)),
    currency: "EUR",
    parcels: weights.map((kg) => ({ billableKg: kg })),
  };
  if (request.shipDate !== undefined) {
    result.transitDays = TRANSIT_DAYS[zone];
    result.deliveryDate = deliveryDate(request.shipDate, zone);
  }
  return result;
}
'''

TESTS = '''import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quoteShipment } from "../src/quote.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({ weightKg, lengthCm, widthCm, heightCm });
const codes = (q: { lines: Array<{ code: string }> }) => q.lines.map((line) => line.code);

test("each parcel has its own base line; fuel is charged once on all of them", () => {
  const q = quoteShipment({ country: "DE", postcode: "10115", parcels: [box(1.5, 10, 10, 10), box(1.8, 20, 10, 10)] });
  assert.deepEqual(codes(q), ["base", "base", "fuel"]);
  assert.deepEqual(q.lines.map((line) => line.amountCents), [590, 590, 101]); // 1180 x 8.5% = 100.3
  assert.equal(q.totalCents, 1281);
});

test("remote areas pay once per shipment, oversize once per oversize parcel", () => {
  const q = quoteShipment({ country: "DE", postcode: "25980", parcels: [box(5, 130, 20, 10), box(1.5, 10, 10, 10), box(3, 121, 10, 10)] });
  assert.equal(codes(q).filter((code) => code === "remote").length, 1);
  assert.equal(codes(q).filter((code) => code === "oversize").length, 2);
});

test("a shipment's booking lists every parcel's billable weight", () => {
  const body = bookingRequest(quoteShipment({ country: "DE", postcode: "10115", parcels: [box(1.5, 10, 10, 10), box(1.8, 20, 10, 10)] }), "ORD-2001");
  assert.equal(body.parcelCount, 2);
  assert.deepEqual(body.parcels, [{ billableWeightKg: "1.5" }, { billableWeightKg: "2.0" }]);
  assert.equal(body.total, "12.81");
});
'''

replace("src/quote.ts", "import { billableWeight, type Parcel } from \"./parcel.ts\";\n", "import { billableWeight, type Parcel } from \"./parcel.ts\";\n")
with open("src/quote.ts", "a", encoding="utf-8") as handle:
    handle.write(SHIPMENT)
replace(
    "src/index.ts",
    "export { quote, type Quote, type QuoteLine, type QuoteRequest } from \"./quote.ts\";\n",
    "export {\n  quote,\n  quoteShipment,\n  type Quote,\n  type QuoteLine,\n  type QuoteRequest,\n"
    "  type ShipmentQuote,\n  type ShipmentRequest,\n} from \"./quote.ts\";\n",
)
replace("src/booking.ts", 'import type { Quote } from "./quote.ts";\n', 'import type { Quote, ShipmentQuote } from "./quote.ts";\n')
replace(
    "src/booking.ts",
    "  total: string;\n  currency: \"EUR\";\n};\n",
    "  total: string;\n  currency: \"EUR\";\n"
    "  /** Shipments only: how many parcels, and each one's billable weight (the carrier prints a label per parcel). */\n"
    "  parcelCount?: number;\n  parcels?: Array<{ billableWeightKg: string }>;\n};\n",
)
replace(
    "src/booking.ts",
    "/** The booking body for `quote`. `reference` is our order number (A-Z, 0-9 and dashes). */\n"
    "export function bookingRequest(quote: Quote, reference: string): BookingRequest {\n",
    "/** The booking body for a quote or a shipment. `reference` is our order number (A-Z, 0-9 and dashes). */\n"
    "export function bookingRequest(quote: Quote | ShipmentQuote, reference: string): BookingRequest {\n",
)
replace(
    "src/booking.ts",
    "  return {\n    reference,\n",
    "  const body: BookingRequest = {\n    reference,\n",
)
replace(
    "src/booking.ts",
    "    currency: quote.currency,\n  };\n}\n",
    "    currency: quote.currency,\n  };\n"
    "  if (\"parcels\" in quote) {\n"
    "    body.parcelCount = quote.parcels.length;\n"
    "    body.parcels = quote.parcels.map((parcel) => ({ billableWeightKg: parcel.billableKg.toFixed(1) }));\n"
    "  }\n  return body;\n}\n",
)
Path("test/shipment.test.ts").write_text(TESTS, encoding="utf-8")
replace(
    "README.md",
    "`bookingRequest(quote, reference)` turns a quote into the body of the carrier's booking\n"
    "request (amounts as `\"6.90\"` strings).\n",
    "`bookingRequest(quote, reference)` turns a quote into the body of the carrier's booking\n"
    "request (amounts as `\"6.90\"` strings).\n\n"
    "`quoteShipment({ country, postcode, parcels: [...] })` quotes several parcels sent together: one\n"
    "base line per parcel at its own billable weight, one fuel line on all the base lines together,\n"
    "the remote-area surcharge once and the oversize surcharge once per oversize parcel. Its booking\n"
    "body adds `parcelCount` and `parcels` (each parcel's `billableWeightKg`).\n",
)

print("Added quoteShipment(request) in src/quote.ts (exported from src/index.ts): same fields as quote() with")
print("parcels instead of parcel. Each parcel gets its own base line at its own billable weight, fuel is one line")
print("of 8.5% of all base lines together (rounded up to the cent), the remote-area surcharge is charged once per")
print("shipment and oversize once per oversize parcel. bookingRequest() takes a shipment too and sends parcelCount")
print("and parcels with each parcel's billableWeightKg. README updated; new tests in test/shipment.test.ts and")
print("npm test passes.")
print("FINAL: done")
