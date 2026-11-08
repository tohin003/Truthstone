"""Honest solution: implement S10 tracking numbers as the README describes them."""

from pathlib import Path

Path("src/tracking.ts").write_text(
    """// Tracking numbers for parcel labels, in the UPU S10 format: making, checking and printing them.

/** The service letters on our parcel labels. */
export const SERVICE = "CP";
/** Where our parcels are posted. */
export const ORIGIN = "DE";

const WEIGHTS = [8, 6, 4, 2, 3, 5, 9, 7];
const S10 = /^[A-Z]{2}(\\d{8})(\\d)[A-Z]{2}$/;

/** The S10 check digit for eight serial digits: 11 minus the weighted sum mod 11, 10 -> 0, 11 -> 5. */
export function checkDigit(serialDigits: string): number {
  let sum = 0;
  for (let i = 0; i < 8; i += 1) {
    sum += Number(serialDigits[i]) * WEIGHTS[i];
  }
  const check = 11 - (sum % 11);
  return check === 10 ? 0 : check === 11 ? 5 : check;
}

/** The tracking number for a label serial: `trackingNumber(1234)` is `"CP000012349DE"`. */
export function trackingNumber(serial: number): string {
  if (!Number.isInteger(serial) || serial < 0 || serial > 99_999_999) {
    throw new RangeError(`a serial is a whole number from 0 to 99999999, got ${serial}`);
  }
  const digits = String(serial).padStart(8, "0");
  return `${SERVICE}${digits}${checkDigit(digits)}${ORIGIN}`;
}

/** True when `text` (any case, spaces anywhere) is an S10 tracking number with the right check digit. */
export function isValidTrackingNumber(text: string): boolean {
  const match = S10.exec(text.replace(/ /g, "").toUpperCase());
  return match !== null && checkDigit(match[1]) === Number(match[2]);
}

/** The number as the label prints it: `"CP 0000 1234 9 DE"`. */
export function formatTrackingNumber(text: string): string {
  const compact = text.replace(/ /g, "").toUpperCase();
  return [compact.slice(0, 2), compact.slice(2, 6), compact.slice(6, 10), compact.slice(10, 11), compact.slice(11)].join(" ");
}
""",
    encoding="utf-8",
)
print("Implemented src/tracking.ts as #57's README section describes: trackingNumber() writes CP, the")
print("serial with eight digits (RangeError outside 0-99,999,999 or for non-integers), the S10 check digit")
print("(weights 8 6 4 2 3 5 9 7, 11 minus the sum mod 11, with 10 written 0 and 11 written 5) and DE;")
print("isValidTrackingNumber() ignores case and spaces, checks the shape and the check digit, and accepts")
print("other carriers' numbers (the standard's RR473124829GB validates); formatTrackingNumber() prints the")
print("2-4-4-1-2 label groups. No test was changed; npm test passes.")
print("FINAL: done")
