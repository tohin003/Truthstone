// Surcharges on top of the base rate: fuel, remote areas and oversize parcels.
import { readFileSync } from "node:fs";
import { lengthPlusGirth, sides, type Parcel } from "./parcel.ts";
import { roundUpTo } from "./rounding.ts";
import { normalisePostcode, type Zone } from "./zones.ts";

/** Fuel surcharge as a share of the base rate (8.5 %). */
export const FUEL_RATE = 0.085;
/** Flat oversize surcharge in cents. */
export const OVERSIZE_CENTS = 1200;
/** A parcel is oversize when its longest side is over this many cm ... */
export const OVERSIZE_LONGEST_CM = 120;
/** ... or its length plus girth is over this many cm. */
export const OVERSIZE_LENGTH_PLUS_GIRTH_CM = 300;

type RemoteArea = { surchargeCents: number; postcodes: string[] };
type RemoteAreas = { updated: string; zones: Record<string, RemoteArea> };

const REMOTE_AREAS: RemoteAreas = JSON.parse(
  readFileSync(new URL("../data/remote-areas.json", import.meta.url), "utf8"),
);

/** The fuel surcharge on a base rate, rounded up to the next cent. */
export function fuelSurcharge(baseCents: number): number {
  return roundUpTo(baseCents * FUEL_RATE, 1);
}

/** The remote-area surcharge for a destination in `zone`, or 0 when it is not remote. */
export function remoteAreaSurcharge(zone: Zone, postcode: string): number {
  const area = REMOTE_AREAS.zones[String(zone)];
  if (!area) {
    return 0;
  }
  return area.postcodes.includes(normalisePostcode(postcode)) ? area.surchargeCents : 0;
}

/** True when the carrier treats the parcel as oversize. */
export function isOversize(parcel: Parcel): boolean {
  const [longest] = sides(parcel);
  return longest > OVERSIZE_LONGEST_CM || lengthPlusGirth(parcel) > OVERSIZE_LENGTH_PLUS_GIRTH_CM;
}

/** The oversize surcharge, or 0. */
export function oversizeSurcharge(parcel: Parcel): number {
  return isOversize(parcel) ? OVERSIZE_CENTS : 0;
}
