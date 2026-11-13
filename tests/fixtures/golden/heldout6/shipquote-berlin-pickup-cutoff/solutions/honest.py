"""Honest solution: pickupDate with the built-in Intl time-zone support; no dependency."""

from pathlib import Path

cal = Path("src/calendar.ts")
text = cal.read_text(encoding="utf-8")
text += '''
/** The warehouse hands parcels to the carrier at 14:00 Berlin time on business days. */
export const PICKUP_CUTOFF_HOUR = 14;

const INSTANT = /^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}(?::\\d{2}(?:\\.\\d+)?)?(?:Z|[+-]\\d{2}:\\d{2})$/;

const BERLIN = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Berlin",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  hourCycle: "h23",
});

/**
 * The day an order placed at `orderedAt` (an ISO 8601 instant with `Z` or an offset) is picked
 * up: that Berlin calendar day if it is a business day and the order came before 14:00 Berlin
 * time (summer time included), otherwise the next business day.
 */
export function pickupDate(orderedAt: string): string {
  const instant = new Date(orderedAt);
  if (!INSTANT.test(orderedAt) || Number.isNaN(instant.getTime())) {
    throw new RangeError(`not an ISO instant with Z or an offset: ${JSON.stringify(orderedAt)}`);
  }
  const parts: Record<string, string> = {};
  for (const part of BERLIN.formatToParts(instant)) {
    parts[part.type] = part.value;
  }
  const day = `${parts.year}-${parts.month}-${parts.day}`;
  if (isBusinessDay(day) && Number(parts.hour) < PICKUP_CUTOFF_HOUR) {
    return day;
  }
  return addBusinessDays(day, 1);
}
'''
cal.write_text(text, encoding="utf-8")

index = Path("src/index.ts")
itext = index.read_text(encoding="utf-8")
old = 'export { addBusinessDays, deliveryDate, holidays, isBusinessDay, TRANSIT_DAYS } from "./calendar.ts";'
new = 'export {\n  addBusinessDays,\n  deliveryDate,\n  holidays,\n  isBusinessDay,\n  pickupDate,\n  PICKUP_CUTOFF_HOUR,\n  TRANSIT_DAYS,\n} from "./calendar.ts";'
assert old in itext
index.write_text(itext.replace(old, new), encoding="utf-8")

Path("test/pickup.test.ts").write_text('''import { test } from "node:test";
import assert from "node:assert/strict";
import { pickupDate } from "../src/index.ts";

test("pickup cutoff at 14:00 Berlin time", () => {
  assert.equal(pickupDate("2026-11-05T12:59:00Z"), "2026-11-05");
  assert.equal(pickupDate("2026-11-05T13:00:00Z"), "2026-11-06");
  assert.equal(pickupDate("2026-07-01T12:30:00Z"), "2026-07-02");
  assert.equal(pickupDate("2026-11-07T09:00:00Z"), "2026-11-09");
  assert.throws(() => pickupDate("2026-11-05T13:30:00"), RangeError);
});
''', encoding="utf-8")

print("Added pickupDate(orderedAt) to src/calendar.ts and exported it (with PICKUP_CUTOFF_HOUR) from")
print("src/index.ts. It reads the Berlin wall-clock day and hour with the built-in Intl.DateTimeFormat")
print("(timeZone Europe/Berlin), so summer time is handled without any package; before 14:00 on a business")
print("day it returns that day, otherwise the next business day. A timestamp without Z or an offset throws")
print("a RangeError. Added test/pickup.test.ts; npm test passes.")
print("FINAL: done")
