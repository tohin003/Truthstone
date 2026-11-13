// The carrier's list as the README describes it: single postcodes and inclusive ranges, per zone.
import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { remoteAreaSurcharge } from "../src/surcharges.ts";

const parcel = { weightKg: 2, lengthCm: 30, widthCm: 20, heightCm: 10 };
const remoteLine = (country: string, postcode: string) =>
  quote({ country, postcode, parcel }).lines.find((line) => line.code === "remote")?.amountCents ?? 0;

test("every postcode of a range pays the zone's surcharge, ends included", () => {
  for (const postcode of ["87567", "87568", "87569"]) {
    assert.equal(remoteAreaSurcharge(3, postcode), 350, postcode);
  }
  for (let n = 25992; n <= 25999; n += 1) {
    assert.equal(remoteAreaSurcharge(1, String(n)), 450, String(n));
  }
  for (const postcode of ["25845", "25846", "25847"]) {
    assert.equal(remoteAreaSurcharge(1, postcode), 450, postcode);
  }
  for (const postcode of ["6991", "6992", "6993"]) {
    assert.equal(remoteAreaSurcharge(4, postcode), 690, postcode);
  }
});

test("postcodes just outside a range, and ordinary ones, pay nothing", () => {
  for (const [zone, postcode] of [[3, "87566"], [3, "87570"], [1, "25991"], [1, "25844"], [1, "25848"], [4, "6990"], [4, "6994"], [1, "10115"], [4, "1010"]] as const) {
    assert.equal(remoteAreaSurcharge(zone, postcode), 0, postcode);
  }
});

test("single postcodes still work, spaces ignored", () => {
  assert.equal(remoteAreaSurcharge(1, "25980"), 450);
  assert.equal(remoteAreaSurcharge(1, " 27498"), 450);
  assert.equal(remoteAreaSurcharge(4, "6561"), 690);
  assert.equal(remoteAreaSurcharge(1, "25 997"), 450);
});

test("quotes carry the remote-area line for postcodes inside a range", () => {
  assert.equal(remoteLine("DE", "87568"), 350);
  assert.equal(remoteLine("DE", "25997"), 450);
  assert.equal(remoteLine("AT", "6993"), 690);
  assert.equal(remoteLine("DE", "87570"), 0);
});
