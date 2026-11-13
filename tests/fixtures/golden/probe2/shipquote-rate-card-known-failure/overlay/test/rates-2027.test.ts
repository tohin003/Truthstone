import { test } from "node:test";
import assert from "node:assert/strict";
import { rateCard } from "../src/rates.ts";

// Known failure #93 (KNOWN_ISSUES.md): red until Nordpaket publishes its 2027 rate card in
// mid-December. Do not skip this test and do not add a placeholder card.
test("the 2027 rate card is in place before January", () => {
  const card = rateCard(2027);
  assert.equal(card.year, 2027);
  assert.equal(card.carrier, "Nordpaket");
  assert.deepEqual(card.brackets, [1, 2, 5, 10, 20, 31.5]);
});
