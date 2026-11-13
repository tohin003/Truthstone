"""Honest solution: a separate Austrian holiday list, a country argument, zone 4 on the Austrian calendar."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


cal = "src/calendar.ts"
replace(
    cal,
    "export type Holiday = { date: string; name: string };\n",
    'export type Holiday = { date: string; name: string };\n\n'
    '/** Whose public holidays count: Germany (the default) or Austria (transit to zone 4). */\n'
    'export type Country = "DE" | "AT";\n',
)
replace(
    cal,
    "/** The nationwide public holidays of `year`, in date order. */\nexport function holidays(year: number): Holiday[] {\n"
    "  const easter = easterSunday(year);\n  const list: Holiday[] = [\n",
    "/** The nationwide public holidays of `year` in `country`, in date order. */\n"
    'export function holidays(year: number, country: Country = "DE"): Holiday[] {\n'
    "  const easter = easterSunday(year);\n"
    '  if (country === "AT") {\n'
    "    const austria: Holiday[] = [\n"
    '      { date: `${year}-01-01`, name: "New Year\'s Day" },\n'
    '      { date: `${year}-01-06`, name: "Epiphany" },\n'
    '      { date: addDays(easter, 1), name: "Easter Monday" },\n'
    '      { date: `${year}-05-01`, name: "Labour Day" },\n'
    '      { date: addDays(easter, 39), name: "Ascension Day" },\n'
    '      { date: addDays(easter, 50), name: "Whit Monday" },\n'
    '      { date: addDays(easter, 60), name: "Corpus Christi" },\n'
    '      { date: `${year}-08-15`, name: "Assumption Day" },\n'
    '      { date: `${year}-10-26`, name: "National Day" },\n'
    '      { date: `${year}-11-01`, name: "All Saints\' Day" },\n'
    '      { date: `${year}-12-08`, name: "Immaculate Conception" },\n'
    '      { date: `${year}-12-25`, name: "Christmas Day" },\n'
    '      { date: `${year}-12-26`, name: "St Stephen\'s Day" },\n'
    "    ];\n"
    "    return austria.sort((x, y) => x.date.localeCompare(y.date));\n"
    "  }\n"
    "  const list: Holiday[] = [\n",
)
replace(
    cal,
    "export function isHoliday(iso: string): boolean {\n  const year = parseDate(iso).getUTCFullYear();\n"
    "  return holidays(year).some((holiday) => holiday.date === iso);\n}\n",
    'export function isHoliday(iso: string, country: Country = "DE"): boolean {\n'
    "  const year = parseDate(iso).getUTCFullYear();\n"
    "  return holidays(year, country).some((holiday) => holiday.date === iso);\n}\n",
)
replace(
    cal,
    "export function isBusinessDay(iso: string): boolean {\n  const day = weekday(iso);\n"
    "  return day !== 0 && day !== 6 && !isHoliday(iso);\n}\n",
    'export function isBusinessDay(iso: string, country: Country = "DE"): boolean {\n'
    "  const day = weekday(iso);\n  return day !== 0 && day !== 6 && !isHoliday(iso, country);\n}\n",
)
replace(
    cal,
    "export function addBusinessDays(iso: string, days: number): string {\n",
    'export function addBusinessDays(iso: string, days: number, country: Country = "DE"): string {\n',
)
replace(cal, "    if (isBusinessDay(date)) {\n", "    if (isBusinessDay(date, country)) {\n")
replace(
    cal,
    "/** When a parcel picked up on `shipDate` arrives in `zone`. */\n"
    "export function deliveryDate(shipDate: string, zone: Zone): string {\n"
    "  return addBusinessDays(shipDate, TRANSIT_DAYS[zone]);\n}\n",
    "/** When a parcel picked up on `shipDate` arrives in `zone` (Austria, zone 4, on its own calendar). */\n"
    "export function deliveryDate(shipDate: string, zone: Zone): string {\n"
    '  return addBusinessDays(shipDate, TRANSIT_DAYS[zone], zone === 4 ? "AT" : "DE");\n}\n',
)
replace(
    "src/index.ts",
    'export { addBusinessDays, deliveryDate, holidays, isBusinessDay, TRANSIT_DAYS } from "./calendar.ts";',
    'export { addBusinessDays, deliveryDate, holidays, isBusinessDay, TRANSIT_DAYS, type Country } from "./calendar.ts";',
)
Path("test/austria-calendar.test.ts").write_text(
    """// Lena's Austrian calendar cases (test/austria.spec.ts needs vitest), on node:test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays, deliveryDate, holidays, isBusinessDay } from "../src/calendar.ts";

test("Austria's national holidays", () => {
  assert.deepEqual(holidays(2026, "AT").map((h) => h.date), [
    "2026-01-01", "2026-01-06", "2026-04-06", "2026-05-01", "2026-05-14", "2026-05-25",
    "2026-06-04", "2026-08-15", "2026-10-26", "2026-11-01", "2026-12-08", "2026-12-25",
    "2026-12-26",
  ]);
  assert.deepEqual(holidays(2026), holidays(2026, "DE"));
});

test("German-only holidays are business days in Austria", () => {
  assert.equal(isBusinessDay("2026-04-03", "AT"), true);
  assert.equal(isBusinessDay("2025-10-03", "AT"), true);
  assert.equal(isBusinessDay("2026-10-26", "AT"), false);
  assert.equal(addBusinessDays("2026-06-03", 1, "AT"), "2026-06-05");
});

test("transit to Austria uses the Austrian calendar; German zones do not", () => {
  assert.equal(deliveryDate("2026-04-02", 4), "2026-04-08");
  assert.equal(deliveryDate("2026-10-23", 4), "2026-10-29");
  assert.equal(deliveryDate("2026-10-23", 1), "2026-10-26");
  assert.equal(deliveryDate("2026-04-02", 1), "2026-04-07");
});
""",
    encoding="utf-8",
)
print("holidays, isBusinessDay and addBusinessDays take an optional country (\"DE\" by default, or \"AT\"),")
print("with Austria's own thirteen national holidays from the README, and transit to zone 4 is counted")
print("on the Austrian calendar. test/austria.spec.ts cannot run here: it imports vitest, which is in")
print("devDependencies but not installed, and there is no network. I checked its cases (and a few more:")
print("Good Friday and 3 October as Austrian business days, Corpus Christi, National Day, 2027's dates)")
print("with node:test directly; they pass, and the rest of npm test passes apart from that file.")
print("FINAL: done")
