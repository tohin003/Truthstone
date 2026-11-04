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

/** What Nordpaket accepts as a booking reference (docs/carrier-booking-api.md). */
const REFERENCE = /^[A-Z0-9-]{4,32}$/;

/**
 * The booking body for `quote`, in the shape of Nordpaket's Booking API v2
 * (docs/carrier-booking-api.md). `reference` is our order number. The carrier takes 4-32
 * characters from A-Z, 0-9 and "-" only: it prints the reference on the label as a Code 39
 * barcode, which has no lower-case letters, and rejects anything else with
 * 422 INVALID_REFERENCE. A reference it would reject throws a RangeError here instead, before
 * the checkout has told the customer that the parcel is booked.
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
