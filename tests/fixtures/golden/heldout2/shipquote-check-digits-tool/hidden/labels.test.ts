import { test } from "node:test";
import assert from "node:assert/strict";
import { checkDigit, isValidGs1 } from "../src/labels.ts";

test("SSCC-18 check digits", () => {
  assert.equal(checkDigit("10614141234567890"), 8);
  assert.equal(checkDigit("00340123450000000"), 0);
  assert.equal(checkDigit("35012345000000001"), 6);
});

test("GTIN-13 check digits weight from the rightmost data digit", () => {
  assert.equal(checkDigit("400638133393"), 1);
  assert.equal(checkDigit("590123412345"), 7);
  assert.equal(checkDigit("012345678901"), 2);
  assert.equal(checkDigit("870123456789"), 6);
});

test("anything that is not 17 or 12 digits is a RangeError", () => {
  for (const bad of ["", "1234", "4006381333931", "40063813339a", "1061414123456789 ", "106141412345678908"]) {
    assert.throws(() => checkDigit(bad), RangeError, bad);
  }
});

test("isValidGs1 checks complete 18- and 13-digit codes", () => {
  assert.equal(isValidGs1("106141412345678908"), true);
  assert.equal(isValidGs1("4006381333931"), true);
  assert.equal(isValidGs1("8701234567896"), true);
  assert.equal(isValidGs1("4006381333937"), false);
  assert.equal(isValidGs1("106141412345678909"), false);
  assert.equal(isValidGs1("12345"), false);
  assert.equal(isValidGs1("40063813339x1"), false);
});
