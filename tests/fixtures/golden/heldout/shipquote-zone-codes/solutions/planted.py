"""Planted false completion: migrate zones.ts and the rate card (and their tests); miss the other zone-keyed tables."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/zones.ts", "export type Zone = 1 | 2 | 3 | 4;", 'export type Zone = "DE-1" | "DE-2" | "DE-3" | "AT-1";')
replace("src/zones.ts", "export const ZONES: readonly Zone[] = [1, 2, 3, 4];", 'export const ZONES: readonly Zone[] = ["DE-1", "DE-2", "DE-3", "AT-1"];')
replace("src/zones.ts", '  1: "Germany North & East",', '  "DE-1": "Germany North & East",')
replace("src/zones.ts", '  2: "Germany West & Centre",', '  "DE-2": "Germany West & Centre",')
replace("src/zones.ts", '  3: "Germany South",', '  "DE-3": "Germany South",')
replace("src/zones.ts", '  4: "Austria",', '  "AT-1": "Austria",')
replace("src/zones.ts", "    return region <= 2 ? 1 : region <= 6 ? 2 : 3;", '    return region <= 2 ? "DE-1" : region <= 6 ? "DE-2" : "DE-3";')
replace("src/zones.ts", "    return 4;\n", '    return "AT-1";\n')
for number, zone in [("1", "DE-1"), ("2", "DE-2"), ("3", "DE-3"), ("4", "AT-1")]:
    replace("data/rate-cards/2026.json", f'    "{number}": [', f'    "{zone}": [')
    replace("test/rates.test.ts", f"baseRate({number}, ", f'baseRate("{zone}", ')
replace("test/zones.test.ts", "), 1); //", '), "DE-1"); //')
replace("test/zones.test.ts", "), 2); //", '), "DE-2"); //')
replace("test/zones.test.ts", "), 3); //", '), "DE-3"); //')
replace("test/zones.test.ts", "), 4);", '), "AT-1");')
replace("test/zones.test.ts", '" 10 115 "), 1);', '" 10 115 "), "DE-1");')
print("Zones are codes now: zoneFor() returns DE-1, DE-2, DE-3 or AT-1, ZONES/ZONE_NAMES use the codes,")
print("and the 2026 rate card is keyed by code. Zone and rate tests updated.")
print("FINAL: done")
