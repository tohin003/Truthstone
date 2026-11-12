// Multi-parcel shipments: several parcels to one destination, priced together (README, 1.7.0).
import type { Parcel } from "./parcel.ts";
import type { QuoteLine } from "./quote.ts";
import type { Zone } from "./zones.ts";

/** The most parcels one shipment may hold. */
export const MAX_PARCELS = 5;

export type ShipmentRequest = {
  country: string;
  postcode: string;
  /** 1 to MAX_PARCELS parcels. */
  parcels: Parcel[];
  /** Which year's rate card to use (default: DEFAULT_YEAR). */
  year?: number;
  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */
  shipDate?: string;
};

export type ShipmentQuote = {
  country: string;
  postcode: string;
  zone: Zone;
  /** Each parcel's billable weight in kg, in the order given. */
  billableKg: number[];
  lines: QuoteLine[];
  totalCents: number;
  currency: "EUR";
  transitDays?: number;
  deliveryDate?: string;
};

/**
 * Quotes a multi-parcel shipment: per-parcel base rates, fuel once on the total base rate,
 * remote-area surcharge once, oversize per oversize parcel. See README, "Multi-parcel shipments".
 */
export function quoteShipment(request: ShipmentRequest): ShipmentQuote {
  // TODO(#58): the API and the tests landed first; the implementation is still to be written.
  throw new Error(`quoteShipment is not implemented yet (${request.parcels.length} parcels)`);
}
