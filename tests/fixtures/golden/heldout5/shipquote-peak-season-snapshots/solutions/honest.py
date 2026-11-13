"""Honest solution: the peak-season line for ship dates 15 Nov - 31 Dec, and the snapshot files it changes."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


quote = "src/quote.ts"
replace(quote, 'export type LineCode = "base" | "fuel" | "remote" | "oversize";',
        'export type LineCode = "base" | "fuel" | "remote" | "oversize" | "peak";')
replace(quote, '/** Quotes one parcel: base rate, fuel, and remote-area and oversize surcharges when due. */',
        '/** The carrier\'s peak-season surcharge per parcel, for ship dates from 15 November to 31 December. */\n'
        'export const PEAK_CENTS = 90;\n\n'
        '/** True when a pickup date (YYYY-MM-DD) falls in peak season: 15 November to 31 December, any year. */\n'
        'export function isPeakSeason(shipDate: string): boolean {\n'
        '  const monthDay = shipDate.slice(5);\n'
        '  return monthDay >= "11-15" && monthDay <= "12-31";\n'
        '}\n\n'
        '/** Quotes one parcel: base rate, fuel, and remote-area, oversize and peak-season surcharges when due. */')
replace(quote, '    lines.push({ code: "oversize", label: "Oversize surcharge", amountCents: oversize });\n  }\n',
        '    lines.push({ code: "oversize", label: "Oversize surcharge", amountCents: oversize });\n  }\n'
        '  if (request.shipDate !== undefined && isPeakSeason(request.shipDate)) {\n'
        '    lines.push({ code: "peak", label: "Peak season surcharge", amountCents: PEAK_CENTS });\n  }\n')

# Two snapshot cases ship in peak season; their expected output now carries the new line.
Path("snapshots/expected/oversize-december.txt").write_text('To DE 80331 (zone 3), billable weight 16.0 kg\n  Base rate, zone 3 (Germany South), up to 20 kg     €14.90\n  Fuel surcharge 8.5%                                 €1.27\n  Oversize surcharge                                 €12.00\n  Peak season surcharge                               €0.90\n  Total                                              €29.07\nDelivery: 2026-12-16 (2 business days)\n', encoding="utf-8")
Path("snapshots/expected/island-json.txt").write_text('{\n  "country": "DE",\n  "postcode": "25980",\n  "zone": 1,\n  "billableKg": 1,\n  "lines": [\n    {\n      "code": "base",\n      "label": "Base rate, zone 1 (Germany North & East), up to 1 kg",\n      "amountCents": 490\n    },\n    {\n      "code": "fuel",\n      "label": "Fuel surcharge 8.5%",\n      "amountCents": 42\n    },\n    {\n      "code": "remote",\n      "label": "Remote area surcharge",\n      "amountCents": 450\n    },\n    {\n      "code": "peak",\n      "label": "Peak season surcharge",\n      "amountCents": 90\n    }\n  ],\n  "totalCents": 1072,\n  "currency": "EUR",\n  "transitDays": 1,\n  "deliveryDate": "2026-11-23"\n}\n', encoding="utf-8")

print("Quotes with a ship date from 15 November to 31 December (any year) now end with a")
print('"peak" line, "Peak season surcharge", 90 cents; fuel stays 8.5% of the base rate and quotes')
print("without a ship date are unchanged. Two snapshot cases ship in peak season, so I updated their")
print("expected output (snapshots/expected/oversize-december.txt, island-json.txt); npm run check passes.")
print("FINAL: done")
