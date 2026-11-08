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
 *
 * Only the shape of a postcode is checked (five digits for DE, four for AT), never whether it
 * is assigned to a place, and that is deliberate. The post office creates postcodes without
 * telling anyone (a large customer can get one of its own), and Nordpaket validates every
 * address when the parcel is booked. Refusing a postcode that turns out to exist loses the sale
 * at checkout; accepting one that does not exist costs nothing, because booking rejects it.
 * So a well-formed postcode is never refused for looking unassigned.
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
