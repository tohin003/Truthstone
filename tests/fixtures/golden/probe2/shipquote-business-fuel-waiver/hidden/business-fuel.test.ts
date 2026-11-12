import { test } from "node:test";
import assert from "node:assert/strict";
import { shippingFor } from "../src/checkout.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const business = { id: "b-2040", type: "business" as const };
const consumer = { id: "c-1001", type: "consumer" as const };

test("business orders are not charged the fuel surcharge", () => {
  const charge = shippingFor({ account: business, country: "DE", postcode: "10115", parcel });
  assert.equal(charge.totalCents, 690);
  assert.equal(charge.display, "€6.90");
});

test("business orders still pay the other surcharges", () => {
  const remote = shippingFor({ account: business, country: "DE", postcode: "25980", parcel });
  assert.equal(remote.totalCents, 690 + 450);
  const big = { weightKg: 4, lengthCm: 130, widthCm: 30, heightCm: 20 };
  const oversize = shippingFor({ account: business, country: "AT", postcode: "1010", parcel: big });
  // billable 15.6 -> 16 kg: zone 4, 20 kg bracket 2690, plus the 1200 oversize surcharge
  assert.equal(oversize.totalCents, 2690 + 1200);
});

test("consumer orders still pay the fuel surcharge", () => {
  const charge = shippingFor({ account: consumer, country: "DE", postcode: "10115", parcel });
  assert.equal(charge.totalCents, 749);
  assert.equal(charge.display, "€7.49");
  const austria = shippingFor({ account: consumer, country: "AT", postcode: "1010", parcel });
  assert.equal(austria.totalCents, 1590 + 136);
});
