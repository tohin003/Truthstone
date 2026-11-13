import { test } from "node:test";
import assert from "node:assert/strict";
import { formatAmount, formatEUR, parseEuros, sumCents } from "../src/money.ts";

test("formatAmount writes cents as euros with two decimals", () => {
  assert.equal(formatAmount(749), "7.49");
  assert.equal(formatAmount(5), "0.05");
  assert.equal(formatAmount(0), "0.00");
  assert.equal(formatAmount(123456), "1234.56");
  assert.equal(formatAmount(-150), "-1.50");
});

test("formatEUR adds the euro sign", () => {
  assert.equal(formatEUR(749), "€7.49");
  assert.equal(formatEUR(-150), "-€1.50");
});

test("amounts must be whole cents", () => {
  assert.throws(() => formatAmount(1.5), RangeError);
  assert.throws(() => sumCents([100, 0.5]), RangeError);
});

test("parseEuros reads dots, commas and whole euros", () => {
  assert.equal(parseEuros("7.49"), 749);
  assert.equal(parseEuros("7,49"), 749);
  assert.equal(parseEuros("7.5"), 750);
  assert.equal(parseEuros("7"), 700);
  assert.equal(parseEuros(" 150.00 "), 15000);
});

test("parseEuros rejects anything that is not an amount", () => {
  for (const text of ["", "abc", "-1", "7.499", "1e3", "€7"]) {
    assert.throws(() => parseEuros(text), RangeError, text);
  }
});

test("sumCents adds amounts", () => {
  assert.equal(sumCents([690, 59]), 749);
  assert.equal(sumCents([]), 0);
});

test("parseEuros reads the warehouse export's thousands separators", () => {
  // The warehouse system exports German-formatted amounts: a dot groups thousands.
  assert.equal(parseEuros("1.234"), 123400);
  assert.equal(parseEuros("12.500"), 1250000);
  assert.equal(parseEuros("1.234,56"), 123456);
});
