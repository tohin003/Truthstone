// The carrier's booking API (v3) rejects a booking whose charges use a code it does not know, a
// label over its length limit, or a total that is not the sum of the charges. This walks every
// zone, weight bracket and surcharge combination, so it is slow: CI runs it (`CI=1 npm test`).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bookingRequest } from "../src/booking.ts";
import { parseEuros } from "../src/money.ts";
import { quote } from "../src/quote.ts";

const carrier = JSON.parse(readFileSync(new URL("../data/carrier.json", import.meta.url), "utf8"));
const skip = process.env.CI ? false : "slow: runs in CI (set CI=1 to run it here)";

const destinations = [
  ["DE", "10115"], ["DE", "25996"], ["DE", "50667"], ["DE", "80331"], ["AT", "1010"], ["AT", "6991"],
];
const weights = [0.4, 1, 1.8, 4.9, 9.5, 14, 19.9, 20, 20.4, 25, 31.5];
const shapes = [[20, 15, 10], [60, 40, 40], [130, 30, 20]];

test("every booking we can produce passes the carrier's v3 validation", { skip }, () => {
  for (const [country, postcode] of destinations) {
    for (const weightKg of weights) {
      for (const [lengthCm, widthCm, heightCm] of shapes) {
        let q;
        try {
          q = quote({ country, postcode, parcel: { weightKg, lengthCm, widthCm, heightCm } });
        } catch {
          continue; // not quotable (over 31.5 kg billable): never booked
        }
        const body = bookingRequest(q, "ORD-0001");
        for (const charge of body.charges) {
          assert.ok(carrier.chargeCodes.includes(charge.code), `unknown charge code ${charge.code}`);
          assert.ok(charge.label.length <= carrier.maxChargeLabelLength, `label too long: ${charge.label}`);
          assert.match(charge.amount, /^\d+\.\d{2}$/);
        }
        const sum = body.charges.reduce((total, charge) => total + parseEuros(charge.amount), 0);
        assert.equal(parseEuros(body.total), sum);
      }
    }
  }
});
