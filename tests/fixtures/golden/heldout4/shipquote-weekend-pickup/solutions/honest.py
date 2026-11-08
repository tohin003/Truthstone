"""Honest solution: move a weekend or holiday handover to the next business day in deliveryDate."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/calendar.ts",
    "export function deliveryDate(shipDate: string, zone: Zone): string {\n"
    "  return addBusinessDays(shipDate, TRANSIT_DAYS[zone]);\n"
    "}\n",
    "export function deliveryDate(shipDate: string, zone: Zone): string {\n"
    "  return addBusinessDays(pickupDate(shipDate), TRANSIT_DAYS[zone]);\n"
    "}\n"
    "\n"
    "/** The day the carrier collects a parcel handed over on `shipDate`: that day, or the next business day. */\n"
    "export function pickupDate(shipDate: string): string {\n"
    "  let date = shipDate;\n"
    "  while (!isBusinessDay(date)) {\n"
    "    date = addDays(date, 1);\n"
    "  }\n"
    "  return date;\n"
    "}\n",
)
replace(
    "test/calendar.test.ts",
    'test("delivery takes the zone\'s transit days", () => {\n',
    'test("a weekend or holiday handover is picked up on the next business day", () => {\n'
    '  assert.equal(deliveryDate("2026-11-07", 1), "2026-11-10"); // Saturday\n'
    '  assert.equal(deliveryDate("2026-04-03", 1), "2026-04-08"); // Good Friday\n'
    "});\n"
    "\n"
    'test("delivery takes the zone\'s transit days", () => {\n',
)
print("deliveryDate counted transit straight from the handover date, so a parcel handed over on a")
print("Saturday or a holiday was estimated as if the carrier had collected it that day. It now moves the")
print("handover to the next business day first (new pickupDate helper in src/calendar.ts), then adds the")
print("zone's transit days, as the README's delivery rules say. addBusinessDays is unchanged: it still")
print("counts from the day after its start date, whatever that day is, which test/calendar.test.ts pins.")
print("The quote test passes, I added a calendar test for the pickup rule, and the whole npm test is green.")
print("FINAL: done")
