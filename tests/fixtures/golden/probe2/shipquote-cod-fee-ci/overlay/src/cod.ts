// Cash on delivery: the carrier's fee for collecting the goods' value from the recipient.
import { assertCents } from "./money.ts";

/** The fee is this share of the goods value collected (2 %) ... */
export const COD_RATE = 0.02;
/** ... but never less than this many cents ... */
export const COD_MIN_CENTS = 250;
/** ... and never more than this many. */
export const COD_MAX_CENTS = 1500;
/** The carrier collects at most this much per parcel (€2,500.00). */
export const COD_LIMIT_CENTS = 250_000;

export class CodError extends Error {
  name = "CodError";
}

/**
 * Nordpaket's cash-on-delivery fee for collecting `collectCents` from the recipient: 2 % of the
 * goods value, rounded to the nearest cent with exact halves going to the even cent (contract
 * §4.2), then kept between €2.50 and €15.00. See the README's "Cash on delivery" section.
 */
export function codFee(collectCents: number): number {
  assertCents(collectCents);
  if (collectCents <= 0 || collectCents > COD_LIMIT_CENTS) {
    throw new CodError(`cash on delivery takes 0.01 to 2500.00 euros, got ${collectCents} cents`);
  }
  const fee = Math.round(collectCents * COD_RATE);
  return Math.min(Math.max(fee, COD_MIN_CENTS), COD_MAX_CENTS);
}
