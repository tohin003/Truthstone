// Kiosk app support: evaluation contexts for the in-store kiosks.
import type { Context } from "./types.ts";

/** Kiosk ids are `kiosk-<city>-<two digits>`, e.g. kiosk-berlin-01. */
const KIOSK_ID = /^kiosk-[a-z]+-\d{2}$/;

/** True for a kiosk's device id. */
export function isKioskId(id: string): boolean {
  return KIOSK_ID.test(id);
}

/** The context a kiosk evaluates flags with: its device id as the user, on the "kiosk" plan. */
export function kioskContext(kioskId: string, country?: string): Context {
  if (!isKioskId(kioskId)) {
    throw new Error(`not a kiosk id: ${JSON.stringify(kioskId)}`);
  }
  return country === undefined ? { userId: kioskId, plan: "kiosk" } : { userId: kioskId, plan: "kiosk", country };
}
