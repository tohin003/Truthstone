// Quotes: the base rate and surcharges for one parcel to one destination, as line items.
import { deliveryDate, TRANSIT_DAYS } from "./calendar.ts";
import { codFee } from "./cod.ts";
import { sumCents } from "./money.ts";
import { billableWeight, type Parcel } from "./parcel.ts";
import { baseRate, DEFAULT_YEAR } from "./rates.ts";
import { FUEL_RATE, fuelSurcharge, oversizeSurcharge, remoteAreaSurcharge } from "./surcharges.ts";
import { normalisePostcode, ZONE_NAMES, zoneFor, type Zone } from "./zones.ts";

export type QuoteRequest = {
  country: string;
  postcode: string;
  parcel: Parcel;
  /** Which year's rate card to use (default: DEFAULT_YEAR). */
  year?: number;
  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */
  shipDate?: string;
  /** Goods value the carrier collects on delivery, in cents; adds the cash-on-delivery fee. */
  codCents?: number;
};

export type LineCode = "base" | "fuel" | "remote" | "oversize" | "cod";

export type QuoteLine = {
  code: LineCode;
  label: string;
  amountCents: number;
};

export type Quote = {
  country: string;
  postcode: string;
  zone: Zone;
  billableKg: number;
  lines: QuoteLine[];
  totalCents: number;
  currency: "EUR";
  transitDays?: number;
  deliveryDate?: string;
};

/** Quotes one parcel: base rate, fuel, and remote-area, oversize and cash-on-delivery charges when due. */
export function quote(request: QuoteRequest): Quote {
  const country = request.country.trim().toUpperCase();
  const postcode = normalisePostcode(request.postcode);
  const zone = zoneFor(country, postcode);
  const billableKg = billableWeight(request.parcel);
  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);

  const lines: QuoteLine[] = [
    {
      code: "base",
      label: `Base rate, zone ${zone} (${ZONE_NAMES[zone]}), up to ${base.bracketKg} kg`,
      amountCents: base.cents,
    },
    {
      code: "fuel",
      label: `Fuel surcharge ${(FUEL_RATE * 100).toFixed(1)}%`,
      amountCents: fuelSurcharge(base.cents),
    },
  ];
  const remote = remoteAreaSurcharge(zone, postcode);
  if (remote > 0) {
    lines.push({ code: "remote", label: "Remote area surcharge", amountCents: remote });
  }
  const oversize = oversizeSurcharge(request.parcel);
  if (oversize > 0) {
    lines.push({ code: "oversize", label: "Oversize surcharge", amountCents: oversize });
  }

  if (request.codCents !== undefined) {
    lines.push({ code: "cod", label: "Cash on delivery fee", amountCents: codFee(request.codCents) });
  }

  const result: Quote = {
    country,
    postcode,
    zone,
    billableKg,
    lines,
    totalCents: sumCents(lines.map((line) => line.amountCents)),
    currency: "EUR",
  };
  if (request.shipDate !== undefined) {
    result.transitDays = TRANSIT_DAYS[zone];
    result.deliveryDate = deliveryDate(request.shipDate, zone);
  }
  return result;
}
