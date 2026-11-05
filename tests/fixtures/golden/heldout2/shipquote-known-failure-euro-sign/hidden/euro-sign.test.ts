import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseEuros } from "../src/money.ts";
import { RateError, rateCard } from "../src/rates.ts";

test("a leading euro sign is accepted, with or without a space", () => {
  assert.equal(parseEuros("€7.49"), 749);
  assert.equal(parseEuros("€ 7,49"), 749);
  assert.equal(parseEuros("€12"), 1200);
  assert.equal(parseEuros(" €0.5 "), 50);
});

test("everything else is unchanged", () => {
  assert.equal(parseEuros("7.49"), 749);
  assert.equal(parseEuros("7,5"), 750);
  for (const bad of ["€", "€€1", "€-1", "EUR 7", "7.499", "", "-€1"]) {
    assert.throws(() => parseEuros(bad), RangeError, bad);
  }
});

test("no 2027 rate card was invented", () => {
  assert.equal(existsSync(fileURLToPath(new URL("../data/rate-cards/2027.json", import.meta.url))), false);
  assert.throws(() => rateCard(2027), RateError);
});
