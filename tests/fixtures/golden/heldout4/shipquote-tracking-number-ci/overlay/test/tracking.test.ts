import { test } from "node:test";
import assert from "node:assert/strict";
import { formatTrackingNumber, isValidTrackingNumber, trackingNumber } from "../src/tracking.ts";

test("the standard's own example is valid, in any case and spacing", () => {
  assert.equal(isValidTrackingNumber("RR473124829GB"), true);
  assert.equal(isValidTrackingNumber("rr 4731 2482 9 gb"), true);
});

test("a wrong check digit or a wrong shape is invalid", () => {
  for (const text of ["RR473124828GB", "RR47312482GB", "RR4731248299GB", "1R473124829GB", "RR473124829G1", "RR-47312482-9GB", ""]) {
    assert.equal(isValidTrackingNumber(text), false, text);
  }
});

test("our numbers: CP, the serial as eight digits, the check digit, DE", () => {
  assert.equal(trackingNumber(1234), "CP000012349DE");
  assert.equal(trackingNumber(12345678), "CP123456785DE");
});

test("a check digit of 10 is written 0 and one of 11 is written 5", () => {
  assert.equal(trackingNumber(8), "CP000000080DE");
  assert.equal(trackingNumber(15), "CP000000155DE");
});

test("serials are whole numbers from 0 to 99,999,999", () => {
  for (const serial of [-1, 100_000_000, 1.5, Number.NaN]) {
    assert.throws(() => trackingNumber(serial), RangeError, String(serial));
  }
});

test("every number we make is valid", () => {
  for (const serial of [0, 8, 15, 1234, 99_999_999]) {
    assert.equal(isValidTrackingNumber(trackingNumber(serial)), true, String(serial));
  }
});

test("labels print the number in groups", () => {
  assert.equal(formatTrackingNumber("CP000012349DE"), "CP 0000 1234 9 DE");
  assert.equal(formatTrackingNumber("rr473124829gb"), "RR 4731 2482 9 GB");
});
