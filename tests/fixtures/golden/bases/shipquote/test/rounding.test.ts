import { test } from "node:test";
import assert from "node:assert/strict";
import { roundUpTo } from "../src/rounding.ts";

test("roundUpTo rounds up to the next step", () => {
  assert.equal(roundUpTo(1.2, 0.5), 1.5);
  assert.equal(roundUpTo(0.2, 0.5), 0.5);
  assert.equal(roundUpTo(2.01, 0.5), 2.5);
  assert.equal(roundUpTo(41.65, 1), 42);
  assert.equal(roundUpTo(75.15, 1), 76);
});

test("roundUpTo leaves values that are already on a step", () => {
  assert.equal(roundUpTo(1.5, 0.5), 1.5);
  assert.equal(roundUpTo(3, 0.5), 3);
  assert.equal(roundUpTo(42, 1), 42);
  assert.equal(roundUpTo(0, 1), 0);
});

test("roundUpTo rejects a step that is not positive, and non-numbers", () => {
  assert.throws(() => roundUpTo(1, 0), RangeError);
  assert.throws(() => roundUpTo(1, -0.5), RangeError);
  assert.throws(() => roundUpTo(Number.NaN, 1), RangeError);
});
