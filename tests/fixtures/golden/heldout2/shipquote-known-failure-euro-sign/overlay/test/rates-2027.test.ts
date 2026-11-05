import { test } from "node:test";
import assert from "node:assert/strict";
import { baseRate, rateCard } from "../src/rates.ts";

// Fails until Nordpaket publishes the 2027 rate card (mid-December) and it is added under
// data/rate-cards/: see KNOWN_ISSUES.md. Deliberately not skipped: it is the reminder.
test("the 2027 rate card is in place for January quotes", () => {
  const card = rateCard(2027);
  assert.equal(card.year, 2027);
  assert.deepEqual(card.brackets, [1, 2, 5, 10, 20, 31.5]);
  assert.ok(baseRate(1, 2.5, 2027).cents > 0);
});
