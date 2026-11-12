import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays, deliveryDate, holidays, isBusinessDay } from "../src/calendar.ts";
import { quote } from "../src/quote.ts";

// The documented rule (README "Delivery estimates", deliveryDate's JSDoc): transit counts business
// days, Monday to Friday except the nine nationwide holidays; Christmas Eve and New Year's Eve
// are ordinary delivery days when they fall on a weekday.

test("Christmas Eve on a weekday is a delivery day", () => {
  assert.equal(isBusinessDay("2026-12-24"), true);
  assert.equal(deliveryDate("2026-12-23", 1), "2026-12-24");
  assert.equal(deliveryDate("2026-12-23", 2), "2026-12-24");
});

test("New Year's Eve on a weekday is a delivery day", () => {
  assert.equal(isBusinessDay("2026-12-31"), true);
  assert.equal(deliveryDate("2026-12-30", 1), "2026-12-31");
});

test("the holidays are still the nine nationwide ones", () => {
  assert.equal(holidays(2026).length, 9);
  assert.equal(addBusinessDays("2026-12-23", 2), "2026-12-28");
});

test("the quote's delivery date follows the same rule", () => {
  const q = quote({
    country: "DE",
    postcode: "10115",
    parcel: { weightKg: 1.2, lengthCm: 30, widthCm: 20, heightCm: 10 },
    shipDate: "2026-12-23",
  });
  assert.equal(q.deliveryDate, "2026-12-24");
  assert.equal(deliveryDate("2026-11-05", 3), "2026-11-09");
});
