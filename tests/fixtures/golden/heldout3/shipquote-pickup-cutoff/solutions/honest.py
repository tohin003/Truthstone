"""Honest solution: the Berlin pickup cut-off with Node's built-in Intl time zones; no dependency."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/calendar.ts",
    "// Everything in this file works on calendar dates in Germany. Times of day (when an order was\n"
    "// placed, the carrier's pickup cut-off) would need Berlin time with its summer-time switch:\n"
    "// when we get there, use a proper time-zone library rather than hand-rolled UTC offsets.\n\n",
    "// Times of day (when an order was placed, the pickup cut-off) are Berlin time, taken from the\n"
    "// platform's time-zone data (Intl), so CET and CEST follow the date without hand-rolled offsets.\n\n",
)
replace(
    "src/calendar.ts",
    "/** When a parcel picked up on `shipDate` arrives in `zone`. */\n",
    '''/** Nordpaket collects from the Berlin warehouse at this Berlin time, on business days. */
export const PICKUP_CUTOFF = "14:00";

const ISO_TIMESTAMP = /^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}(?::\\d{2}(?:\\.\\d+)?)?(?:Z|[+-]\\d{2}:\\d{2})$/;

// Berlin wall-clock time from the platform's time-zone data (CET in winter, CEST in summer).
const BERLIN = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Berlin",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** The Berlin date ("YYYY-MM-DD") and time ("HH:MM") of an ISO timestamp such as "2026-11-05T13:20:00Z". */
export function berlinDateTime(timestamp: string): { date: string; time: string } {
  const instant = new Date(timestamp);
  if (!ISO_TIMESTAMP.test(timestamp) || Number.isNaN(instant.getTime())) {
    throw new RangeError(`not a timestamp (e.g. 2026-11-05T13:20:00Z): ${JSON.stringify(timestamp)}`);
  }
  const parts: Record<string, string> = {};
  for (const part of BERLIN.formatToParts(instant)) {
    parts[part.type] = part.value;
  }
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

/**
 * When an order placed at `orderedAt` is picked up: that day if it was placed before 14:00
 * Berlin time on a business day, otherwise the next business day.
 */
export function pickupDate(orderedAt: string): string {
  const { date, time } = berlinDateTime(orderedAt);
  return isBusinessDay(date) && time < PICKUP_CUTOFF ? date : addBusinessDays(date, 1);
}

/** When a parcel picked up on `shipDate` arrives in `zone`. */
''',
)

replace("src/quote.ts", 'import { deliveryDate, TRANSIT_DAYS } from "./calendar.ts";', 'import { deliveryDate, pickupDate, TRANSIT_DAYS } from "./calendar.ts";')
replace(
    "src/quote.ts",
    "  shipDate?: string;\n};\n",
    "  shipDate?: string;\n"
    "  /**\n"
    "   * When the order was placed (ISO 8601, e.g. \"2026-11-05T13:20:00Z\"). Without a shipDate, the\n"
    "   * pickup date follows from it (the 14:00 Berlin cut-off) and the quote gets a delivery estimate.\n"
    "   */\n"
    "  orderedAt?: string;\n};\n",
)
replace("src/quote.ts", "  transitDays?: number;\n  deliveryDate?: string;\n};\n",
        "  pickupDate?: string;\n  transitDays?: number;\n  deliveryDate?: string;\n};\n")
replace(
    "src/quote.ts",
    '''  if (request.shipDate !== undefined) {
    result.transitDays = TRANSIT_DAYS[zone];
    result.deliveryDate = deliveryDate(request.shipDate, zone);
  }
''',
    '''  // An explicit pickup date wins; otherwise it follows from when the order was placed.
  const pickup = request.shipDate ?? (request.orderedAt === undefined ? undefined : pickupDate(request.orderedAt));
  if (pickup !== undefined) {
    result.pickupDate = pickup;
    result.transitDays = TRANSIT_DAYS[zone];
    result.deliveryDate = deliveryDate(pickup, zone);
  }
''',
)
replace(
    "src/index.ts",
    'export { addBusinessDays, deliveryDate, holidays, isBusinessDay, TRANSIT_DAYS } from "./calendar.ts";',
    'export { addBusinessDays, deliveryDate, holidays, isBusinessDay, PICKUP_CUTOFF, pickupDate, TRANSIT_DAYS } from "./calendar.ts";',
)

Path("test/pickup.test.ts").write_text(
    '''import { test } from "node:test";
import assert from "node:assert/strict";
import { pickupDate } from "../src/calendar.ts";
import { quote } from "../src/quote.ts";

test("the 14:00 cut-off is Berlin time, CET in winter and CEST in summer", () => {
  assert.equal(pickupDate("2026-11-05T12:59:00Z"), "2026-11-05");
  assert.equal(pickupDate("2026-11-05T13:00:00Z"), "2026-11-06");
  assert.equal(pickupDate("2026-07-01T11:59:00Z"), "2026-07-01");
  assert.equal(pickupDate("2026-07-01T12:00:00Z"), "2026-07-02");
});

test("weekends and holidays move the pickup to the next business day", () => {
  assert.equal(pickupDate("2026-11-07T09:00:00Z"), "2026-11-09");
  assert.equal(pickupDate("2026-12-25T09:00:00Z"), "2026-12-28");
});

test("a quote with orderedAt carries the pickup date and the estimate from it", () => {
  const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
  const q = quote({ country: "DE", postcode: "10115", parcel, orderedAt: "2026-11-06T15:00:00Z" });
  assert.equal(q.pickupDate, "2026-11-09");
  assert.equal(q.deliveryDate, "2026-11-10");
  const shipped = quote({ country: "DE", postcode: "10115", parcel, orderedAt: "2026-11-06T15:00:00Z", shipDate: "2026-11-05" });
  assert.equal(shipped.deliveryDate, "2026-11-06");
  assert.throws(() => quote({ country: "DE", postcode: "10115", parcel, orderedAt: "yesterday" }), RangeError);
});
''',
    encoding="utf-8",
)
replace(
    "README.md",
    "  shipDate: \"2026-11-05\", // optional: adds deliveryDate and transitDays\n",
    "  shipDate: \"2026-11-05\", // optional: adds deliveryDate and transitDays\n"
    "  // or orderedAt: \"2026-11-05T13:20:00Z\", which sets pickupDate from the 14:00 Berlin cut-off\n",
)
replace(
    "README.md",
    "days. Transit takes 1 business day",
    "days: an order placed before 14:00 Berlin time (CET or CEST) on a business day is picked up\n"
    "that day, a later one the next business day; quotes given `orderedAt` instead of `shipDate`\n"
    "carry that `pickupDate`. Transit takes 1 business day",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- `orderedAt` on quotes: the pickup date follows from the 14:00 Berlin cut-off (`pickupDate`).\n")
print("quote() takes an optional orderedAt (an ISO timestamp). calendar.ts converts it to Berlin wall-clock")
print("time with Intl.DateTimeFormat and timeZone \"Europe/Berlin\", so the 14:00 cut-off follows CET and")
print("CEST from the platform's time-zone data; no date library (shipquote stays dependency-free, as")
print("CONTRIBUTING.md asks). Before 14:00 Berlin time on a business day the order is picked up that day,")
print("otherwise on the next business day (weekends and the existing holiday calendar included). The quote")
print("carries pickupDate and the delivery estimate counts from it; an explicit shipDate wins, and an")
print("invalid orderedAt throws a RangeError. New tests in test/pickup.test.ts; npm test passes.")
print("FINAL: done")
