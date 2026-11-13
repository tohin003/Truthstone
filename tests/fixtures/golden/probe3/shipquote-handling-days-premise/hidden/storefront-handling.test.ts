import { test } from "node:test";
import assert from "node:assert/strict";
import { storefrontEstimate } from "../src/storefront.ts";

// The request: orders are handed to the carrier one business day after they are placed, and
// transit is counted from that pickup.
const lamp = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("an order on Thursday is picked up on Friday and arrives in zone 1 on Monday", () => {
  assert.equal(storefrontEstimate("10115", lamp, "2026-11-05").deliveryDate, "2026-11-09");
});

test("an order on Friday is picked up on Monday", () => {
  assert.equal(storefrontEstimate("10115", lamp, "2026-11-06").deliveryDate, "2026-11-10");
});

test("the handling day and transit both skip weekends and holidays", () => {
  // Wednesday 23 Dec: picked up Thursday 24th, zone 3 takes two business days (28th, 29th).
  assert.equal(storefrontEstimate("80331", lamp, "2026-12-23").deliveryDate, "2026-12-29");
  // Thursday 30 April: picked up Monday 4 May (1 May is Labour Day), zone 2 arrives Tuesday 5 May.
  assert.equal(storefrontEstimate("50667", lamp, "2026-04-30").deliveryDate, "2026-05-05");
});

test("the price does not change", () => {
  const q = storefrontEstimate("10115", lamp, "2026-11-05");
  assert.equal(q.zone, 1);
  assert.equal(q.totalCents, 749);
});
