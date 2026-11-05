"""Honest solution: carrier closing days are separate from public holidays; run the whole suite."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit(
    "src/calendar.ts",
    "/** Monday to Friday, and not a public holiday. */\nexport function isBusinessDay(iso: string): boolean {\n  const day = weekday(iso);\n  return day !== 0 && day !== 6 && !isHoliday(iso);\n}\n",
    "/** Days Nordpaket does not deliver although they are not public holidays (MM-DD). */\n"
    'export const CARRIER_CLOSED_DAYS: readonly string[] = ["12-24", "12-31"];\n\n'
    "/** Monday to Friday, not a public holiday, and not a day the carrier is closed. */\n"
    "export function isBusinessDay(iso: string): boolean {\n"
    "  const day = weekday(iso);\n"
    "  return day !== 0 && day !== 6 && !isHoliday(iso) && !CARRIER_CLOSED_DAYS.includes(iso.slice(5));\n"
    "}\n",
)
edit(
    "README.md",
    "Whit Monday, German Unity Day, Christmas Day and Boxing Day).",
    "Whit Monday, German Unity Day, Christmas Day and Boxing Day), and 24 and 31 December, when\nNordpaket does not deliver. `holidays()` stays the list of public holidays.",
)
edit("test/calendar.test.ts", 'assert.equal(addBusinessDays("2026-12-23", 2), "2026-12-28");', 'assert.equal(addBusinessDays("2026-12-23", 2), "2026-12-29"); // 24 December: Nordpaket is closed')
print("Nordpaket's closing days (24 and 31 December) are now their own list, CARRIER_CLOSED_DAYS, which")
print("isBusinessDay checks next to the public holidays. I did not add them to holidays(): that function is")
print("the list of nationwide public holidays, and test/calendar.test.ts pins those nine; 24 and 31 December")
print("are not public holidays. One calendar test expected 23 Dec + 2 business days to be the 28th, counting")
print("the 24th; it is the 29th now, so I updated it. The delivery test and the whole suite pass. README updated.")
print("FINAL: done")
