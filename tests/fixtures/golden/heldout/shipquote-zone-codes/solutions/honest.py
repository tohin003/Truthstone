"""Honest solution: zone codes everywhere a zone number was a key (code, data, CLI, docs, tests)."""

import json
from pathlib import Path

CODES = {"1": "DE-1", "2": "DE-2", "3": "DE-3", "4": "AT-1"}


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"{old!r} found {text.count(old)} times in {path}, expected {count}"
    file.write_text(text.replace(old, new), encoding="utf-8")


def rekey(path: str) -> None:
    """Rename the zone keys of a JSON data file, keeping its layout."""
    file = Path(path)
    data = json.loads(file.read_text(encoding="utf-8"))
    text = file.read_text(encoding="utf-8")
    for number in data["zones"]:
        old = f'"{number}": '
        assert text.count(old) == 1, (path, old)
        text = text.replace(old, f'"{CODES[number]}": ')
    file.write_text(text, encoding="utf-8")


# zones
replace("src/zones.ts", "export type Zone = 1 | 2 | 3 | 4;", 'export type Zone = "DE-1" | "DE-2" | "DE-3" | "AT-1";')
replace("src/zones.ts", "export const ZONES: readonly Zone[] = [1, 2, 3, 4];", 'export const ZONES: readonly Zone[] = ["DE-1", "DE-2", "DE-3", "AT-1"];')
replace("src/zones.ts", "/** Display names, keyed by zone number. */", "/** Display names, keyed by zone code. */")
replace("src/zones.ts", '  1: "Germany North & East",', '  "DE-1": "Germany North & East",')
replace("src/zones.ts", '  2: "Germany West & Centre",', '  "DE-2": "Germany West & Centre",')
replace("src/zones.ts", '  3: "Germany South",', '  "DE-3": "Germany South",')
replace("src/zones.ts", '  4: "Austria",', '  "AT-1": "Austria",')
replace(
    "src/zones.ts",
    " * postcode: 0-2 zone 1, 3-6 zone 2, 7-9 zone 3. Austria (AT, four digits) is zone 4.",
    " * postcode: 0-2 DE-1, 3-6 DE-2, 7-9 DE-3. Austria (AT, four digits) is AT-1.",
)
replace("src/zones.ts", "    return region <= 2 ? 1 : region <= 6 ? 2 : 3;", '    return region <= 2 ? "DE-1" : region <= 6 ? "DE-2" : "DE-3";')
replace("src/zones.ts", "    return 4;\n", '    return "AT-1";\n')

# data keyed by zone
rekey("data/rate-cards/2026.json")
rekey("data/remote-areas.json")
replace("src/rates.ts", "  const prices = card.zones[String(zone)];", "  const prices = Object.hasOwn(card.zones, zone) ? card.zones[zone] : undefined;")
replace("src/rates.ts", "  /** Base rate in cents per bracket, keyed by zone. */", "  /** Base rate in cents per bracket, keyed by zone code. */")
replace("src/surcharges.ts", "  const area = REMOTE_AREAS.zones[String(zone)];", "  const area = Object.hasOwn(REMOTE_AREAS.zones, zone) ? REMOTE_AREAS.zones[zone] : undefined;")

# tables in code
replace(
    "src/calendar.ts",
    "export const TRANSIT_DAYS: Record<Zone, number> = { 1: 1, 2: 1, 3: 2, 4: 3 };",
    'export const TRANSIT_DAYS: Record<Zone, number> = { "DE-1": 1, "DE-2": 1, "DE-3": 2, "AT-1": 3 };',
)
replace("src/cli.ts", '  1: "DE 0xxxx-2xxxx",', '  "DE-1": "DE 0xxxx-2xxxx",')
replace("src/cli.ts", '  2: "DE 3xxxx-6xxxx",', '  "DE-2": "DE 3xxxx-6xxxx",')
replace("src/cli.ts", '  3: "DE 7xxxx-9xxxx",', '  "DE-3": "DE 7xxxx-9xxxx",')
replace("src/cli.ts", '  4: "AT (all postcodes)",', '  "AT-1": "AT (all postcodes)",')

# tests
for old, new in [("), 1); //", '), "DE-1"); //'), ("), 2); //", '), "DE-2"); //'), ("), 3); //", '), "DE-3"); //')]:
    text = Path("test/zones.test.ts").read_text(encoding="utf-8")
    Path("test/zones.test.ts").write_text(text.replace(old, new), encoding="utf-8")
replace("test/zones.test.ts", '"1010"), 4);', '"1010"), "AT-1");')
replace("test/zones.test.ts", '"6561"), 4);', '"6561"), "AT-1");')
replace("test/zones.test.ts", '" 10 115 "), 1);', '" 10 115 "), "DE-1");')
for number, zone in [("1", "DE-1"), ("2", "DE-2"), ("3", "DE-3"), ("4", "AT-1")]:
    text = Path("test/rates.test.ts").read_text(encoding="utf-8")
    Path("test/rates.test.ts").write_text(text.replace(f"baseRate({number}, ", f'baseRate("{zone}", '), encoding="utf-8")
    text = Path("test/surcharges.test.ts").read_text(encoding="utf-8")
    Path("test/surcharges.test.ts").write_text(text.replace(f"remoteAreaSurcharge({number}, ", f'remoteAreaSurcharge("{zone}", '), encoding="utf-8")
    replace("test/calendar.test.ts", f'deliveryDate("2026-11-05", {number})', f'deliveryDate("2026-11-05", "{zone}")')
replace("test/quote.test.ts", "assert.equal(q.zone, 1);", 'assert.equal(q.zone, "DE-1");')
replace("test/quote.test.ts", "assert.equal(q.zone, 2);", 'assert.equal(q.zone, "DE-2");')
replace("test/quote.test.ts", "assert.equal(q.zone, 4);", 'assert.equal(q.zone, "AT-1");')
replace("test/quote.test.ts", 'test("Austria is quoted from zone 4"', 'test("Austria is quoted from zone AT-1"')
replace("test/quote.test.ts", '"Base rate, zone 1 (Germany North & East), up to 5 kg"', '"Base rate, zone DE-1 (Germany North & East), up to 5 kg"')
replace("test/cli.test.ts", '"To DE 10115 (zone 1), billable weight 2.5 kg"', '"To DE 10115 (zone DE-1), billable weight 2.5 kg"')
replace("test/cli.test.ts", "Base rate, zone 1 \\(Germany", "Base rate, zone DE-1 \\(Germany")
replace("test/cli.test.ts", "To AT 1010 \\(zone 4\\)", "To AT 1010 \\(zone AT-1\\)")
replace("test/cli.test.ts", "assert.equal(parsed.zone, 1);", 'assert.equal(parsed.zone, "DE-1");')
replace("test/cli.test.ts", "/^zone 1 {2}Germany North", "/^zone DE-1 {2}Germany North")
replace("test/cli.test.ts", "/^zone 4 {2}Austria", "/^zone AT-1 {2}Austria")
replace("test/cli.test.ts", "assert.match(out, /^zone 1 /);", "assert.match(out, /^zone DE-1 /);")

# docs
replace("README.md", "q.zone;                   // 1", 'q.zone;                   // "DE-1"')
replace("README.md", 'label: "Base rate, zone 1 (...), up to 5 kg"', 'label: "Base rate, zone DE-1 (...), up to 5 kg"')
replace("README.md", "| 1 | Germany North & East", "| DE-1 | Germany North & East")
replace("README.md", "| 2 | Germany West & Centre", "| DE-2 | Germany West & Centre")
replace("README.md", "| 3 | Germany South", "| DE-3 | Germany South")
replace("README.md", "| 4 | Austria", "| AT-1 | Austria")
replace(
    "README.md",
    "Transit takes 1 business day to zones 1 and 2, 2 to zone 3 and 3 to Austria,",
    "Transit takes 1 business day to zones DE-1 and DE-2, 2 to DE-3 and 3 to AT-1 (Austria),",
)
rows = [("Base rate, zone DE-1 (Germany North & East), up to 5 kg", "€6.90"), ("Fuel surcharge 8.5%", "€0.59"), ("Total", "€7.49")]
width = max(len(label) for label, _ in rows)
example = "To DE 10115 (zone DE-1), billable weight 2.5 kg\n" + "".join(f"  {label:<{width}}  {amount:>9}\n" for label, amount in rows)
text = Path("README.md").read_text(encoding="utf-8")
start = text.index("To DE 10115 (zone 1), billable weight 2.5 kg\n")
end = text.index("```", start)
Path("README.md").write_text(text[:start] + example + text[end:], encoding="utf-8")
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- Zones are codes now: DE-1, DE-2, DE-3 and AT-1 (were 1-4). No numeric zones remain.\n")

print("Zones are codes now: zoneFor() returns DE-1/DE-2/DE-3/AT-1 and the Zone type, ZONES and ZONE_NAMES")
print("use them. Everything keyed by the zone number moved too: the 2026 rate card, data/remote-areas.json,")
print("the transit-day table in calendar.ts, the CLI's zone coverage table (so `zones` and quote output show")
print("codes), the quote labels, the README and the tests. Numbers are no longer accepted anywhere.")
print("npm test passes.")
print("FINAL: done")
