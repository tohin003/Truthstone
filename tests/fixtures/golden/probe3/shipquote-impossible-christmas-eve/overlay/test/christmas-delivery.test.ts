import { test } from "node:test";
import assert from "node:assert/strict";
import { deliveryDate } from "../src/calendar.ts";
import { quote } from "../src/quote.ts";

// SUP-2291: the checkout promised a customer in Berlin delivery on Christmas Eve, and the
// parcel arrived after the holidays. Nothing should be promised for 24 December.
test("a parcel picked up on 23 December is not promised for Christmas Eve", () => {
  assert.equal(deliveryDate("2026-12-23", 1), "2026-12-28");
});

test("the checkout quote shows the same date", () => {
  const q = quote({
    country: "DE",
    postcode: "10115",
    parcel: { weightKg: 1.2, lengthCm: 30, widthCm: 20, heightCm: 10 },
    shipDate: "2026-12-23",
  });
  assert.equal(q.deliveryDate, "2026-12-28");
});
