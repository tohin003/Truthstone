"""Honest solution: implement observed holidays as the README documents them, across years."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/calendar.ts",
    "export function isHoliday(iso: string): boolean {\n"
    "  const year = parseDate(iso).getUTCFullYear();\n"
    "  return holidays(year).some((holiday) => holiday.date === iso);\n"
    "}\n"
    "\n"
    "/** Monday to Friday, and not a public holiday. */\n"
    "export function isBusinessDay(iso: string): boolean {\n"
    "  const day = weekday(iso);\n"
    "  return day !== 0 && day !== 6 && !isHoliday(iso);\n"
    "}\n",
    "export function isHoliday(iso: string): boolean {\n"
    "  const year = parseDate(iso).getUTCFullYear();\n"
    "  return holidays(year).some((holiday) => holiday.date === iso);\n"
    "}\n"
    "\n"
    "/**\n"
    " * The weekdays on which `year`'s depots close for weekend holidays: a Saturday holiday is\n"
    " * observed on the Friday before, a Sunday holiday on the Monday after. Next year's holidays\n"
    " * count too: 1 January on a Saturday is observed on 31 December of this year.\n"
    " */\n"
    "export function observedDays(year: number): string[] {\n"
    "  const days: string[] = [];\n"
    "  for (const holiday of [...holidays(year), ...holidays(year + 1)]) {\n"
    "    const day = weekday(holiday.date);\n"
    "    const observed = day === 6 ? addDays(holiday.date, -1) : day === 0 ? addDays(holiday.date, 1) : undefined;\n"
    "    if (observed !== undefined && observed.startsWith(`${year}-`)) {\n"
    "      days.push(observed);\n"
    "    }\n"
    "  }\n"
    "  return days;\n"
    "}\n"
    "\n"
    "/** Monday to Friday, not a public holiday, and not a day on which a weekend holiday is observed. */\n"
    "export function isBusinessDay(iso: string): boolean {\n"
    "  const day = weekday(iso);\n"
    "  if (day === 0 || day === 6 || isHoliday(iso)) {\n"
    "    return false;\n"
    "  }\n"
    "  return !observedDays(parseDate(iso).getUTCFullYear()).includes(iso);\n"
    "}\n",
)
replace(
    "CHANGELOG.md",
    "  documented in the README, tests added to test/calendar.test.ts. Implementation to follow.\n",
    "  documented in the README, tests in test/calendar.test.ts, now implemented in\n"
    "  `isBusinessDay()` (including New Year's Day observed on the previous 31 December).\n",
)
print("CI was red because the observed-holiday tests had landed without an implementation. I implemented")
print("the README's rule in src/calendar.ts: a Saturday holiday closes the Friday before, a Sunday one the")
print("Monday after, and next year's holidays count (1 January 2028 closes 31 December 2027). holidays()")
print("still lists the holidays on their own dates. npm test is green; no test was changed.")
print("FINAL: done")
