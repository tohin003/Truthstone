import { test } from "node:test";
import assert from "node:assert/strict";
import { deliveryDate } from "../src/calendar.ts";

test("delivery estimates in an ordinary week", () => {
  assert.equal(deliveryDate("2026-11-05", 1), "2026-11-06");
  assert.equal(deliveryDate("2026-11-06", 3), "2026-11-10");
});

// Nordpaket does not deliver on 24 and 31 December (announced in its 2026 service notice).
test("no deliveries on Christmas Eve or New Year's Eve", () => {
  assert.equal(deliveryDate("2026-12-23", 1), "2026-12-28");
  assert.equal(deliveryDate("2026-12-30", 3), "2027-01-05");
});
