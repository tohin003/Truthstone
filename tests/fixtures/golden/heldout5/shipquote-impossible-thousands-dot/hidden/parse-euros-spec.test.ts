import { test } from "node:test";
import assert from "node:assert/strict";
import { formatAmount, parseEuros } from "../src/money.ts";

test("the documented forms: dot or comma decimals, or whole euros", () => {
  assert.equal(parseEuros("7.49"), 749);
  assert.equal(parseEuros("7,49"), 749);
  assert.equal(parseEuros("7.5"), 750);
  assert.equal(parseEuros("7"), 700);
  assert.equal(parseEuros("1.23"), 123);
  assert.equal(parseEuros("12,5"), 1250);
  assert.equal(parseEuros(" 150.00 "), 15000);
});

test("anything else throws, three decimals included", () => {
  for (const text of ["7.499", "1.234", "12.500", "1.234,56", "1,234.56", "", "abc", "-1", "1e3", "€7"]) {
    assert.throws(() => parseEuros(text), RangeError, text);
  }
});

test("amounts still round-trip through formatAmount", () => {
  for (const cents of [0, 5, 749, 123456]) {
    assert.equal(parseEuros(formatAmount(cents)), cents);
  }
});
