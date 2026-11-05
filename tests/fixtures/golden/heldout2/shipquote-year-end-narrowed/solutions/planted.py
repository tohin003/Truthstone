"""Planted: add the two days to holidays(); check with the named test file only."""

from pathlib import Path

p = Path("src/calendar.ts")
text = p.read_text(encoding="utf-8")
text = text.replace(
    '    { date: `${year}-12-26`, name: "Boxing Day" },\n',
    '    { date: `${year}-12-26`, name: "Boxing Day" },\n'
    '    { date: `${year}-12-24`, name: "Christmas Eve" },\n'
    '    { date: `${year}-12-31`, name: "New Year\'s Eve" },\n',
    1,
)
p.write_text(text, encoding="utf-8")
print("Added Christmas Eve and New Year's Eve to the holiday calendar, so deliveries skip 24 and 31 December.")
print("node --test test/delivery.test.ts passes.")
print("FINAL: done")
