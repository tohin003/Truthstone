// Booking requests: the body we POST to the carrier's booking API for a quoted parcel.
import { formatAmount } from "./money.ts";
import type { Quote } from "./quote.ts";

export type BookingCharge = {
  code: string;
  label: string;
  /** Euros with two decimals, e.g. "6.90". */
  amount: string;
};

export type BookingRequest = {
  reference: string;
  service: "parcel";
  destination: { country: string; postcode: string };
  /** One decimal, e.g. "2.5". */
  billableWeightKg: string;
  charges: BookingCharge[];
  total: string;
  currency: "EUR";
};

const REFERENCE = /^[A-Z0-9-]{4,32}$/;

/**
 * The booking body for `quote`. `reference` is our order number.
 *
 * Nordpaket's booking API takes references of 4-32 characters from A-Z, 0-9 and "-" only;
 * anything else, lower case included, is answered 422 and the parcel is not booked. A reference
 * is never rewritten either (no upper-casing, no trimming): the carrier prints it on the label
 * and echoes it in every tracking event, and the warehouse scanners match it byte for byte
 * against our order numbers. A reference that does not fit is fixed where order numbers are
 * issued, so this throws a RangeError instead of sending it (Booking API v2, section 3.1).
 */
export function bookingRequest(quote: Quote, reference: string): BookingRequest {
  if (!REFERENCE.test(reference)) {
    throw new RangeError(`booking references are 4-32 of A-Z, 0-9 and "-", got ${JSON.stringify(reference)}`);
  }
  return {
    reference,
    service: "parcel",
    destination: { country: quote.country, postcode: quote.postcode },
    billableWeightKg: quote.billableKg.toFixed(1),
    charges: quote.lines.map(({ amountCents, ...line }) => ({ ...line, amount: formatAmount(amountCents) })),
    total: formatAmount(quote.totalCents),
    currency: quote.currency,
  };
}
