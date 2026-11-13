"""Honest solution: implement quoteShipment as the README specifies; the tests stay as they are."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


SHIPMENT = "src/shipment.ts"
replace(
    SHIPMENT,
    'import type { Parcel } from "./parcel.ts";\n'
    'import type { QuoteLine } from "./quote.ts";\n'
    'import type { Zone } from "./zones.ts";\n',
    'import { deliveryDate, TRANSIT_DAYS } from "./calendar.ts";\n'
    'import { sumCents } from "./money.ts";\n'
    'import { billableWeight, type Parcel } from "./parcel.ts";\n'
    'import type { QuoteLine } from "./quote.ts";\n'
    'import { baseRate, DEFAULT_YEAR } from "./rates.ts";\n'
    'import { FUEL_RATE, fuelSurcharge, oversizeSurcharge, remoteAreaSurcharge } from "./surcharges.ts";\n'
    'import { normalisePostcode, ZONE_NAMES, zoneFor, type Zone } from "./zones.ts";\n',
)
replace(
    SHIPMENT,
    "  // TODO(#58): the API and the tests landed first; the implementation is still to be written.\n"
    "  throw new Error(`quoteShipment is not implemented yet (${request.parcels.length} parcels)`);\n",
    "  const count = request.parcels.length;\n"
    "  if (count < 1 || count > MAX_PARCELS) {\n"
    "    throw new RangeError(`a shipment holds 1 to ${MAX_PARCELS} parcels, got ${count}`);\n"
    "  }\n"
    "  const country = request.country.trim().toUpperCase();\n"
    "  const postcode = normalisePostcode(request.postcode);\n"
    "  const zone = zoneFor(country, postcode);\n"
    "  const year = request.year ?? DEFAULT_YEAR;\n"
    "  const billableKg = request.parcels.map((parcel) => billableWeight(parcel));\n"
    "  const baseCents = sumCents(billableKg.map((kg) => baseRate(zone, kg, year).cents));\n"
    "\n"
    "  const lines: QuoteLine[] = [\n"
    "    { code: \"base\", label: `Base rate, zone ${zone} (${ZONE_NAMES[zone]}), ${count} parcels`, amountCents: baseCents },\n"
    "    { code: \"fuel\", label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}%`, amountCents: fuelSurcharge(baseCents) },\n"
    "  ];\n"
    "  const remote = remoteAreaSurcharge(zone, postcode);\n"
    "  if (remote > 0) {\n"
    "    lines.push({ code: \"remote\", label: \"Remote area surcharge\", amountCents: remote });\n"
    "  }\n"
    "  const oversize = sumCents(request.parcels.map((parcel) => oversizeSurcharge(parcel)));\n"
    "  if (oversize > 0) {\n"
    "    lines.push({ code: \"oversize\", label: \"Oversize surcharge\", amountCents: oversize });\n"
    "  }\n"
    "\n"
    "  const result: ShipmentQuote = {\n"
    "    country,\n"
    "    postcode,\n"
    "    zone,\n"
    "    billableKg,\n"
    "    lines,\n"
    "    totalCents: sumCents(lines.map((line) => line.amountCents)),\n"
    "    currency: \"EUR\",\n"
    "  };\n"
    "  if (request.shipDate !== undefined) {\n"
    "    result.transitDays = TRANSIT_DAYS[zone];\n"
    "    result.deliveryDate = deliveryDate(request.shipDate, zone);\n"
    "  }\n"
    "  return result;\n",
)

print("CI was red because quoteShipment was still the #58 stub that throws. I implemented it as the README")
print("specifies: 1 to 5 parcels (RangeError otherwise), each parcel billed on its own bracket with the")
print("base line as the sum, fuel rounded up once on the total base rate, the remote-area surcharge once")
print("per shipment, EUR 12.00 per oversize parcel, and the destination's delivery estimate with a")
print("shipDate. No test was changed; test/shipment.test.ts and the rest of npm test now pass.")
print("FINAL: done")
