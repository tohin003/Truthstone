import { test } from "node:test";
import assert from "node:assert/strict";
import { shippingFor } from "../src/checkout.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const consumer = { id: "c-1001", type: "consumer" as const };

test("a consumer order is charged the carrier quote", () => {
  const charge = shippingFor({ account: consumer, country: "DE", postcode: "10115", parcel });
  assert.equal(charge.totalCents, 749);
  assert.equal(charge.display, "€7.49");
  assert.deepEqual(
    charge.quote.lines.map((line) => line.code),
    ["base", "fuel"],
  );
});

test("remote destinations add the remote-area surcharge to the charge", () => {
  const charge = shippingFor({ account: consumer, country: "DE", postcode: "25980", parcel });
  assert.equal(charge.totalCents, 690 + 59 + 450);
});

test("a scheduled pickup date gives the order a delivery estimate", () => {
  const charge = shippingFor({ account: consumer, country: "AT", postcode: "1010", parcel, shipDate: "2026-11-05" });
  assert.equal(charge.quote.zone, 4);
  assert.equal(typeof charge.quote.deliveryDate, "string");
});
