// GS1 check digits for the parcel labels (Mia). Run with `npm run test:labels` (vitest).
import { describe, expect, it } from "vitest";
import { checkDigit, isValidGs1 } from "../src/labels.ts";

const rangeError = (run: () => unknown) => {
  try {
    run();
  } catch (error) {
    return error instanceof RangeError;
  }
  return false;
};

describe("checkDigit", () => {
  it("computes SSCC-18 check digits (17 data digits)", () => {
    expect(checkDigit("10614141234567890")).toBe(8);
    expect(checkDigit("00340123450000000")).toBe(0);
    expect(checkDigit("35012345000000001")).toBe(6);
  });

  it("computes GTIN-13 check digits (12 data digits)", () => {
    expect(checkDigit("400638133393")).toBe(1);
    expect(checkDigit("590123412345")).toBe(7);
    expect(checkDigit("012345678901")).toBe(2);
  });

  it("rejects anything else", () => {
    for (const bad of ["", "1234", "4006381333931", "40063813339a", "1061414123456789 "]) {
      expect(rangeError(() => checkDigit(bad))).toBe(true);
    }
  });
});

describe("isValidGs1", () => {
  it("accepts complete codes with the right check digit", () => {
    expect(isValidGs1("106141412345678908")).toBe(true);
    expect(isValidGs1("4006381333931")).toBe(true);
    expect(isValidGs1("4006381333937")).toBe(false);
    expect(isValidGs1("106141412345678909")).toBe(false);
    expect(isValidGs1("12345")).toBe(false);
  });
});
