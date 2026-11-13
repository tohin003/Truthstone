import { test } from "node:test";
import assert from "node:assert/strict";
import { formatEUR } from "../src/money.ts";

// Finance: amounts shown to people group thousands with commas.
test("formatEUR groups thousands with commas", () => {
  assert.equal(formatEUR(123456), "€1,234.56");
  assert.equal(formatEUR(100000000), "€1,000,000.00");
  assert.equal(formatEUR(99999), "€999.99");
  assert.equal(formatEUR(-250000), "-€2,500.00");
});
