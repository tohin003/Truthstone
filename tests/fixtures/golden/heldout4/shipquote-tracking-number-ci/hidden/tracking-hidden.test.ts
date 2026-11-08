import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { formatTrackingNumber, isValidTrackingNumber, trackingNumber } from "../src/tracking.ts";

test("check digits for other serials", () => {
  assert.equal(trackingNumber(4711), "CP000047113DE");
  assert.equal(trackingNumber(31415926), "CP314159268DE");
  assert.equal(trackingNumber(27182818), "CP271828189DE");
  assert.equal(trackingNumber(10000000), "CP100000003DE");
});

test("10 is written 0 and 11 is written 5, at the edges too", () => {
  assert.equal(trackingNumber(20261108), "CP202611080DE");
  assert.equal(trackingNumber(27), "CP000000270DE");
  assert.equal(trackingNumber(0), "CP000000005DE");
  assert.equal(trackingNumber(99_999_999), "CP999999995DE");
  assert.equal(trackingNumber(34), "CP000000345DE");
});

test("serials outside 0 to 99,999,999, or not whole, are refused", () => {
  for (const serial of [-5, 123_456_789, 2.25, Number.POSITIVE_INFINITY]) {
    assert.throws(() => trackingNumber(serial), RangeError, String(serial));
  }
});

test("validation: other carriers, any case, spaces anywhere", () => {
  for (const text of ["RR473124829GB", "CP000047113DE", "cp 0000 4711 3 de", " C P 3141 5926 8 D E ", "EE123456785US", "CP202611080DE"]) {
    assert.equal(isValidTrackingNumber(text), true, text);
  }
});

test("validation: wrong digits, letters or lengths", () => {
  for (const text of [
    "CP000047114DE",
    "CP000047131DE",
    "CP0000471130DE",
    "CP00047113DE",
    "C1000047113DE",
    "CP000047113D",
    "CP00004711XDE",
    "CP0000-4711-3DE",
  ]) {
    assert.equal(isValidTrackingNumber(text), false, text);
  }
});

test("the label form", () => {
  assert.equal(formatTrackingNumber("CP202611080DE"), "CP 2026 1108 0 DE");
  assert.equal(formatTrackingNumber("ee 1234 5678 5 us"), "EE 1234 5678 5 US");
  for (const serial of [0, 27, 4711, 99_999_999]) {
    const number = trackingNumber(serial);
    assert.equal(isValidTrackingNumber(formatTrackingNumber(number)), true, number);
    assert.equal(formatTrackingNumber(number).replace(/ /g, ""), number);
  }
});

test("quotes are unchanged", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });
  assert.equal(q.totalCents, 749);
});
