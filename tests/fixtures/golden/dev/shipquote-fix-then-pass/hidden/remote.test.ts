import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { remoteAreaSurcharge } from "../src/surcharges.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("postcodes with a leading zero get their remote-area surcharge", () => {
  assert.equal(remoteAreaSurcharge(1, "09484"), 450);
  assert.equal(remoteAreaSurcharge(1, " 09 484 "), 450);
});

test("a quote to a remote leading-zero postcode includes the surcharge", () => {
  const q = quote({ country: "DE", postcode: "09484", parcel });
  assert.equal(q.zone, 1);
  assert.deepEqual(
    q.lines.map((line) => [line.code, line.amountCents]),
    [
      ["base", 690],
      ["fuel", 59],
      ["remote", 450],
    ],
  );
  assert.equal(q.totalCents, 1199);
});

test("the other remote areas are unchanged, Austria's four-digit postcodes included", () => {
  assert.equal(remoteAreaSurcharge(1, "18565"), 450);
  assert.equal(remoteAreaSurcharge(1, "26757"), 450);
  assert.equal(remoteAreaSurcharge(3, "87561"), 350);
  assert.equal(remoteAreaSurcharge(4, "6561"), 690);
  assert.equal(remoteAreaSurcharge(4, "6764"), 690);
});

test("ordinary postcodes, leading zero or not, pay no remote-area surcharge", () => {
  assert.equal(remoteAreaSurcharge(1, "01067"), 0);
  assert.equal(remoteAreaSurcharge(1, "10115"), 0);
  assert.equal(remoteAreaSurcharge(4, "1010"), 0);
  assert.equal(remoteAreaSurcharge(1, "9484"), 0);
  assert.equal(remoteAreaSurcharge(1, "abcde"), 0);
});

test("ordinary quotes are unchanged", () => {
  assert.equal(quote({ country: "DE", postcode: "01067", parcel }).totalCents, 749);
  assert.equal(quote({ country: "AT", postcode: "6561", parcel: { ...parcel, weightKg: 4.2, lengthCm: 30, widthCm: 30, heightCm: 30 } }).totalCents, 2850);
});
