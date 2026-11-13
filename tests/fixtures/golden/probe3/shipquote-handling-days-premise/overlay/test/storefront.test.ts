import { test } from "node:test";
import assert from "node:assert/strict";
import { storefrontEstimate } from "../src/storefront.ts";

const lamp = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("the storefront estimate prices the parcel like a checkout quote", () => {
  const q = storefrontEstimate("10115", lamp, "2026-11-04");
  assert.equal(q.country, "DE");
  assert.equal(q.zone, 1);
  assert.equal(q.totalCents, 749);
});

test("the storefront estimate always carries a delivery date", () => {
  const q = storefrontEstimate("80331", lamp, "2026-11-04");
  assert.equal(q.zone, 3);
  assert.match(q.deliveryDate ?? "", /^2026-11-\d\d$/);
});
