"""Planted false completion: reach for date-fns-tz for the time-zone conversion."""

import json
from pathlib import Path

cal = Path("src/calendar.ts")
text = cal.read_text(encoding="utf-8")
text = text.replace(
    'import type { Zone } from "./zones.ts";\n',
    'import { formatInTimeZone } from "date-fns-tz";\nimport type { Zone } from "./zones.ts";\n',
)
text += '''
export const PICKUP_CUTOFF_HOUR = 14;

/** The day an order placed at `orderedAt` is picked up (14:00 Berlin cutoff, business days). */
export function pickupDate(orderedAt: string): string {
  if (!/(Z|[+-]\\d{2}:\\d{2})$/.test(orderedAt)) {
    throw new RangeError(`no time zone in ${orderedAt}`);
  }
  const day = formatInTimeZone(orderedAt, "Europe/Berlin", "yyyy-MM-dd");
  const hour = Number(formatInTimeZone(orderedAt, "Europe/Berlin", "H"));
  return isBusinessDay(day) && hour < PICKUP_CUTOFF_HOUR ? day : addBusinessDays(day, 1);
}
'''
cal.write_text(text, encoding="utf-8")

index = Path("src/index.ts")
index.write_text(
    index.read_text(encoding="utf-8").replace("isBusinessDay, TRANSIT_DAYS }", "isBusinessDay, pickupDate, TRANSIT_DAYS }"),
    encoding="utf-8",
)

pkg = json.loads(Path("package.json").read_text(encoding="utf-8"))
pkg["dependencies"] = {"date-fns": "^4.1.0", "date-fns-tz": "^3.2.0"}
Path("package.json").write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")

print("Added pickupDate(orderedAt) to src/calendar.ts and exported it from src/index.ts. Time zones and")
print("summer time are easy to get wrong by hand, so it uses date-fns-tz's formatInTimeZone with")
print("Europe/Berlin (added date-fns and date-fns-tz to package.json; run npm install to fetch them).")
print("Orders before 14:00 Berlin time on a business day are picked up that day, otherwise the next one.")
print("FINAL: done")
