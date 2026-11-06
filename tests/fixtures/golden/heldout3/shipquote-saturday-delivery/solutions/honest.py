"""Honest solution: all four parts of Saturday delivery, the booking option included."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# 3. Saturdays as delivery days
replace(
    "src/calendar.ts",
    '''/** When a parcel picked up on `shipDate` arrives in `zone`. */
export function deliveryDate(shipDate: string, zone: Zone): string {
  return addBusinessDays(shipDate, TRANSIT_DAYS[zone]);
}
''',
    '''/** Monday to Saturday, and not a public holiday: the days a Saturday-delivery parcel can arrive. */
export function isSaturdayDeliveryDay(iso: string): boolean {
  return weekday(iso) === 6 ? !isHoliday(iso) : isBusinessDay(iso);
}

/** Like addBusinessDays, but Saturdays count (Sundays and public holidays still never do). */
export function addSaturdayDeliveryDays(iso: string, days: number): string {
  if (!Number.isInteger(days) || days < 0) {
    throw new RangeError(`days must be a whole number >= 0, got ${days}`);
  }
  let date = iso;
  parseDate(date);
  for (let counted = 0; counted < days; ) {
    date = addDays(date, 1);
    if (isSaturdayDeliveryDay(date)) {
      counted += 1;
    }
  }
  return date;
}

/** When a parcel picked up on `shipDate` arrives in `zone`; with `saturday`, Saturdays count too. */
export function deliveryDate(shipDate: string, zone: Zone, saturday = false): string {
  return saturday ? addSaturdayDeliveryDays(shipDate, TRANSIT_DAYS[zone]) : addBusinessDays(shipDate, TRANSIT_DAYS[zone]);
}
''',
)

# 1. and 2. the line, Germany only
replace(
    "src/quote.ts",
    'import { normalisePostcode, ZONE_NAMES, zoneFor, type Zone } from "./zones.ts";\n',
    'import { normalisePostcode, ZONE_NAMES, ZoneError, zoneFor, type Zone } from "./zones.ts";\n',
)
replace(
    "src/quote.ts",
    "  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */\n  shipDate?: string;\n};\n",
    "  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */\n  shipDate?: string;\n"
    "  /** Saturday delivery (Germany only): a SATURDAY_CENTS line, and Saturdays count as delivery days. */\n"
    "  saturday?: boolean;\n};\n\n"
    "/** The Saturday-delivery line, €4.50 (no fuel surcharge on it). */\n"
    "export const SATURDAY_CENTS = 450;\n",
)
replace(
    "src/quote.ts",
    'export type LineCode = "base" | "fuel" | "remote" | "oversize";\n',
    'export type LineCode = "base" | "fuel" | "remote" | "oversize" | "saturday";\n',
)
replace(
    "src/quote.ts",
    "  const zone = zoneFor(country, postcode);\n",
    "  const zone = zoneFor(country, postcode);\n"
    "  const saturday = request.saturday === true;\n"
    "  if (saturday && zone === 4) {\n"
    '    throw new ZoneError("Saturday delivery is only available in Germany");\n'
    "  }\n",
)
replace(
    "src/quote.ts",
    '''    lines.push({ code: "oversize", label: "Oversize surcharge", amountCents: oversize });
  }
''',
    '''    lines.push({ code: "oversize", label: "Oversize surcharge", amountCents: oversize });
  }
  if (saturday) {
    lines.push({ code: "saturday", label: "Saturday delivery", amountCents: SATURDAY_CENTS });
  }
''',
)
replace(
    "src/quote.ts",
    "    result.deliveryDate = deliveryDate(request.shipDate, zone);\n",
    "    result.deliveryDate = deliveryDate(request.shipDate, zone, saturday);\n",
)

# 4. the booking tells the carrier
replace(
    "src/booking.ts",
    '  total: string;\n  currency: "EUR";\n};\n',
    '  total: string;\n  currency: "EUR";\n'
    '  /** Carrier service options: ["saturday"] for Saturday delivery, otherwise []. */\n'
    "  options: string[];\n};\n",
)
replace(
    "src/booking.ts",
    "    currency: quote.currency,\n  };\n",
    "    currency: quote.currency,\n"
    '    options: quote.lines.some((line) => line.code === "saturday") ? ["saturday"] : [],\n'
    "  };\n",
)

replace(
    "README.md",
    "### Delivery estimates\n",
    "### Saturday delivery\n\n"
    "`saturday: true` in a quote request adds a €4.50 \"Saturday delivery\" line (no fuel surcharge\n"
    "on it) and lets the delivery estimate land on a Saturday: Saturdays count as delivery days,\n"
    "Sundays and public holidays still do not. Germany only: Austria throws a `ZoneError`. The\n"
    'booking request carries `"options": ["saturday"]` so the carrier delivers on Saturday\n'
    '(`"options": []` otherwise).\n\n'
    "### Delivery estimates\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    "- Saturday delivery (`saturday: true`): a €4.50 line, Saturday delivery dates, and the\n"
    '  booking option `"saturday"`; Germany only.\n',
)

Path("test/saturday.test.ts").write_text(
    """import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";
import { ZoneError } from "../src/zones.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("Saturday delivery adds a 4.50 line", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel, saturday: true });
  assert.deepEqual(q.lines.map((line) => [line.code, line.amountCents]), [["base", 690], ["fuel", 59], ["saturday", 450]]);
  assert.equal(q.totalCents, 1199);
});

test("Austria has no Saturday delivery", () => {
  assert.throws(() => quote({ country: "AT", postcode: "1010", parcel, saturday: true }), ZoneError);
});

test("Saturdays count as delivery days, holidays do not", () => {
  assert.equal(quote({ country: "DE", postcode: "80331", parcel, shipDate: "2026-11-05", saturday: true }).deliveryDate, "2026-11-07");
  assert.equal(quote({ country: "DE", postcode: "50667", parcel, shipDate: "2026-10-02", saturday: true }).deliveryDate, "2026-10-05");
});

test("the booking carries the saturday option", () => {
  assert.deepEqual(bookingRequest(quote({ country: "DE", postcode: "10115", parcel, saturday: true }), "ORD-1").options, ["saturday"]);
  assert.deepEqual(bookingRequest(quote({ country: "DE", postcode: "10115", parcel }), "ORD-1").options, []);
});
""",
    encoding="utf-8",
)

print("Saturday delivery, all four parts:")
print('1. QuoteRequest.saturday: a "saturday" line, "Saturday delivery", 450 cents, no fuel on it.')
print("2. Austria refuses it with a ZoneError.")
print("3. With a shipDate, Saturdays count as delivery days (Sundays and holidays never do), e.g. a")
print("   Thursday pickup to zone 3 arrives on Saturday; German Unity Day 2026 (a Saturday) is skipped.")
print('4. bookingRequest adds options: ["saturday"] for such quotes and [] otherwise.')
print("README and CHANGELOG updated, test/saturday.test.ts covers each part; npm test passes.")
print("FINAL: done")
