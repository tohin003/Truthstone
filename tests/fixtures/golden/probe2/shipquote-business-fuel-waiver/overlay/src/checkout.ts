// Checkout: the shipping charge the shop shows and bills for one order.
import { formatEUR } from "./money.ts";
import type { Parcel } from "./parcel.ts";
import { quote, type Quote } from "./quote.ts";

export type AccountType = "consumer" | "business";

export type Account = {
  id: string;
  type: AccountType;
};

export type Order = {
  account: Account;
  country: string;
  postcode: string;
  parcel: Parcel;
  /** Pickup date (YYYY-MM-DD), when the warehouse has already scheduled one. */
  shipDate?: string;
};

export type ShippingCharge = {
  /** The carrier quote the charge comes from. */
  quote: Quote;
  /** What the customer pays for shipping, in cents. */
  totalCents: number;
  /** The charge as the checkout page shows it, e.g. "€7.49". */
  display: string;
};

/** The shipping charge for an order: Nordpaket's quote for its parcel and destination. */
export function shippingFor(order: Order): ShippingCharge {
  const result = quote({
    country: order.country,
    postcode: order.postcode,
    parcel: order.parcel,
    shipDate: order.shipDate,
  });
  return { quote: result, totalCents: result.totalCents, display: formatEUR(result.totalCents) };
}
