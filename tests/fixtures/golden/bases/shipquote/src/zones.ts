// Shipping zones: which zone a destination country and postcode belong to.

export type Zone = 1 | 2 | 3 | 4;

/** Every zone, in order. */
export const ZONES: readonly Zone[] = [1, 2, 3, 4];

/** Display names, keyed by zone number. */
export const ZONE_NAMES: Record<Zone, string> = {
  1: "Germany North & East",
  2: "Germany West & Centre",
  3: "Germany South",
  4: "Austria",
};

export class ZoneError extends Error {
  name = "ZoneError";
}

/** Strips the spaces people type into postcodes: " 10 115 " -> "10115". */
export function normalisePostcode(postcode: string): string {
  return postcode.replace(/\s+/g, "");
}

/**
 * The zone for a destination. Germany (DE) is split by the first digit of its five-digit
 * postcode: 0-2 zone 1, 3-6 zone 2, 7-9 zone 3. Austria (AT, four digits) is zone 4.
 */
export function zoneFor(country: string, postcode: string): Zone {
  const code = normalisePostcode(postcode);
  const destination = country.trim().toUpperCase();
  if (destination === "DE") {
    if (!/^\d{5}$/.test(code)) {
      throw new ZoneError(`not a German postcode: ${JSON.stringify(postcode)}`);
    }
    const region = Number(code[0]);
    return region <= 2 ? 1 : region <= 6 ? 2 : 3;
  }
  if (destination === "AT") {
    if (!/^\d{4}$/.test(code)) {
      throw new ZoneError(`not an Austrian postcode: ${JSON.stringify(postcode)}`);
    }
    return 4;
  }
  throw new ZoneError(`we do not ship to ${JSON.stringify(country)}`);
}
