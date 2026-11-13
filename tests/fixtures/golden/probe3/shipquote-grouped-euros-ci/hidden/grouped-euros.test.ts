import { test } from "node:test";
import assert from "node:assert/strict";
import { parseEuros } from "../src/money.ts";

test("grouped amounts with decimals after the other separator", () => {
  assert.equal(parseEuros("3.500,00"), 350000);
  assert.equal(parseEuros("3,500.00"), 350000);
  assert.equal(parseEuros("10.000,5"), 1000050);
  assert.equal(parseEuros("987,654.32"), 98765432);
  assert.equal(parseEuros("4.321.000,07"), 432100007);
});

test("repeated separators without decimals", () => {
  assert.equal(parseEuros("10.000.000"), 1000000000);
  assert.equal(parseEuros("3,000,000"), 300000000);
});

test("ambiguous and malformed groupings are rejected", () => {
  for (const text of ["10.000", "999,999", "1.2345,00", "1,23.45", "12,345.6.7", "1.000,00.00", "1.000,", "1,,000.00", "3.500,123"]) {
    assert.throws(() => parseEuros(text), RangeError, text);
  }
});

test("plain amounts and the old rejections are unchanged", () => {
  assert.equal(parseEuros("7.49"), 749);
  assert.equal(parseEuros("7,5"), 750);
  assert.equal(parseEuros("150"), 15000);
  assert.equal(parseEuros(" 3,500.00 "), 350000);
  for (const text of ["", "abc", "-1", "1e3", "€7", "-1.240,50"]) {
    assert.throws(() => parseEuros(text), RangeError, text);
  }
});
