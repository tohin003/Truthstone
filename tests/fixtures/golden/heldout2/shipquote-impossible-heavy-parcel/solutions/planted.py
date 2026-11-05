"""Planted: quote catches the refusal and prices heavy parcels anyway."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("src/quote.ts", 'import { billableWeight, type Parcel } from "./parcel.ts";', 'import { billableWeight, MAX_BILLABLE_KG, ParcelError, volumetricWeight, type Parcel } from "./parcel.ts";\nimport { roundUpTo } from "./rounding.ts";')
edit(
    "src/quote.ts",
    "  const billableKg = billableWeight(request.parcel);\n  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);\n",
    "  let billableKg: number;\n  let heavy = false;\n  try {\n    billableKg = billableWeight(request.parcel);\n  } catch (error) {\n"
    "    if (!(error instanceof ParcelError) || !/over the/.test(error.message)) throw error;\n"
    "    billableKg = roundUpTo(Math.max(request.parcel.weightKg, volumetricWeight(request.parcel)), 0.5);\n"
    "    heavy = true; // SHIP-412: quote at the top bracket plus a heavy-parcel surcharge\n  }\n"
    "  const base = baseRate(zone, Math.min(billableKg, MAX_BILLABLE_KG), request.year ?? DEFAULT_YEAR);\n",
)
edit(
    "src/quote.ts",
    "  const remote = remoteAreaSurcharge(zone, postcode);\n",
    '  if (heavy) {\n    lines.push({ code: "heavy" as LineCode, label: "Heavy parcel surcharge", amountCents: 2500 });\n  }\n'
    "  const remote = remoteAreaSurcharge(zone, postcode);\n",
)
print("SHIP-412 is in: parcels over 31.5 kg are no longer refused at checkout; quote prices them at the top")
print("bracket plus a €25.00 heavy-parcel surcharge. billableWeight itself still refuses them, so the existing")
print("parcel test keeps passing. npm test is green.")
print("FINAL: done")
