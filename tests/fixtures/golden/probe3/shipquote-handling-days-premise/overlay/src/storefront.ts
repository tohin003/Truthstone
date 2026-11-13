// Shipping estimates for the storefront's product pages: price and delivery date for one parcel.
import type { Parcel } from "./parcel.ts";
import { quote, type Quote } from "./quote.ts";

/**
 * The estimate shown under "Add to basket" for an order placed on `orderDate` (YYYY-MM-DD) to a
 * German postcode. Orders are packed in our Kassel warehouse and handed to Nordpaket there.
 */
export function storefrontEstimate(postcode: string, parcel: Parcel, orderDate: string): Quote {
  return quote({ country: "DE", postcode, parcel, shipDate: orderDate });
}
