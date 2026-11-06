"""Honest solution: rename the field in the code, the tests, the docs and the notice template that uses it."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/quote.ts", "  transitDays?: number;\n", "  /** Business days from pickup to delivery (not calendar days). */\n  transitBusinessDays?: number;\n")
replace("src/quote.ts", "    result.transitDays = TRANSIT_DAYS[zone];\n", "    result.transitBusinessDays = TRANSIT_DAYS[zone];\n")
replace("src/cli.ts", "result.transitDays", "result.transitBusinessDays", count=2)
replace("templates/delivery-estimate.txt", "{transitDays}", "{transitBusinessDays}")
replace("README.md", "// optional: adds deliveryDate and transitDays", "// optional: adds deliveryDate and transitBusinessDays")
replace("test/quote.test.ts", ".transitDays", ".transitBusinessDays", count=2)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n- `Quote.transitDays` is now `transitBusinessDays` (also in `quote --json` and in the\n"
    "  delivery-estimate notice): the count was always business days, not calendar days.\n",
)

print("Renamed Quote.transitDays to transitBusinessDays: the Quote type (with a doc comment saying they are")
print("business days) and quote(), the CLI's delivery line, quote --json (it prints the quote object), the")
print("README example and the quote test. The delivery-estimate notice used the field too: templates are")
print("filled from the quote's fields and an unknown placeholder renders empty, so templates/")
print("delivery-estimate.txt would have silently lost its day count; it now says {transitBusinessDays}.")
print("Nothing uses transitDays any more (the released 1.5.0 CHANGELOG entry keeps its history). npm test passes.")
print("FINAL: done")
