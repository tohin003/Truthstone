import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";
import { fuelSurcharge } from "../src/surcharges.ts";

const carrier = JSON.parse(readFileSync(new URL("../data/carrier.json", import.meta.url), "utf8"));
const OLD = ["base", "fuel", "remote", "oversize"];
const box = (weightKg: number, lengthCm = 40, widthCm = 30, heightCm = 20) => ({ weightKg, lengthCm, widthCm, heightCm });
const extra = (q: ReturnType<typeof quote>) => q.lines.filter((line) => !OLD.includes(line.code));
const byCode = (q: ReturnType<typeof quote>, code: string) => q.lines.find((line) => line.code === code);

test("over 20 kg billable: one flat 3.50 handling line", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(22) });
  assert.equal(q.billableKg, 22);
  const lines = extra(q);
  assert.equal(lines.length, 1);
  assert.equal(lines[0].amountCents, 350);
  assert.equal(q.totalCents, q.lines.reduce((sum, line) => sum + line.amountCents, 0));
});

test("the handling fee is not subject to fuel", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel: box(30) });
  assert.equal(byCode(q, "fuel")!.amountCents, fuelSurcharge(byCode(q, "base")!.amountCents));
});

test("billable weight decides, and exactly 20 kg is not over", () => {
  assert.equal(extra(quote({ country: "DE", postcode: "10115", parcel: box(20) })).length, 0);
  assert.equal(extra(quote({ country: "DE", postcode: "10115", parcel: box(19.6) })).length, 0);
  // 12 kg actual, 80x60x50 cm: volumetric 48 kg is too heavy; 70x50x40: 28 kg volumetric.
  const bulky = quote({ country: "DE", postcode: "50667", parcel: box(12, 70, 50, 40) });
  assert.equal(bulky.billableKg, 28);
  assert.equal(extra(bulky).length, 1);
});

test("the handling line uses a charge code the carrier's booking API accepts", () => {
  const q = quote({ country: "DE", postcode: "25996", parcel: box(25) });
  const body = bookingRequest(q, "ORD-7001");
  for (const charge of body.charges) {
    assert.ok(carrier.chargeCodes.includes(charge.code), `the carrier rejects charge code ${charge.code}`);
    assert.ok(charge.label.length <= carrier.maxChargeLabelLength);
  }
  assert.equal(body.charges.length, 4);
});

test("parcels up to 20 kg are unchanged", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  assert.deepEqual(q.lines.map((line) => [line.code, line.amountCents]), [["base", 690], ["fuel", 59]]);
  assert.equal(q.totalCents, 749);
});
