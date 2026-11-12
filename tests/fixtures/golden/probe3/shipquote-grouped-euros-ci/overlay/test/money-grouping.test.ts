import { test } from "node:test";
import assert from "node:assert/strict";
import { parseEuros } from "../src/money.ts";

test("thousands separators with decimals, in either convention", () => {
  assert.equal(parseEuros("1.240,50"), 124050);
  assert.equal(parseEuros("1,240.50"), 124050);
  assert.equal(parseEuros("12.345.678,9"), 1234567890);
  assert.equal(parseEuros("1,000,000.01"), 100000001);
});

test("a separator used more than once groups thousands", () => {
  assert.equal(parseEuros("1.240.000"), 124000000);
  assert.equal(parseEuros("2,500,000"), 250000000);
});

test("a single separator before three digits is ambiguous", () => {
  for (const text of ["1.240", "1,240", "7.499"]) {
    assert.throws(() => parseEuros(text), RangeError, text);
  }
});

test("badly grouped amounts are rejected", () => {
  for (const text of ["1.24.000", "12.40,00", "1.240.50", "1,240,5", ".240,50", "1..240,50", "1.240,500", "1.240,50,00"]) {
    assert.throws(() => parseEuros(text), RangeError, text);
  }
});

test("ungrouped amounts read as before", () => {
  assert.equal(parseEuros("7,49"), 749);
  assert.equal(parseEuros("12"), 1200);
  assert.equal(parseEuros(" 1.240,50 "), 124050);
});
