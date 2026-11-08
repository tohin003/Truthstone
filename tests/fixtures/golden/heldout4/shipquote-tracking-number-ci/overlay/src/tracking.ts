// Tracking numbers for parcel labels, in the UPU S10 format: making, checking and printing them.

/** The service letters on our parcel labels. */
export const SERVICE = "CP";
/** Where our parcels are posted. */
export const ORIGIN = "DE";

/** The tracking number for a label serial: `trackingNumber(1234)` is `"CP000012349DE"`. */
export function trackingNumber(serial: number): string {
  throw new Error("trackingNumber is not implemented yet (#57)");
}

/** True when `text` (any case, spaces anywhere) is an S10 tracking number with the right check digit. */
export function isValidTrackingNumber(text: string): boolean {
  throw new Error("isValidTrackingNumber is not implemented yet (#57)");
}

/** The number as the label prints it: `"CP 0000 1234 9 DE"`. */
export function formatTrackingNumber(text: string): string {
  throw new Error("formatTrackingNumber is not implemented yet (#57)");
}
