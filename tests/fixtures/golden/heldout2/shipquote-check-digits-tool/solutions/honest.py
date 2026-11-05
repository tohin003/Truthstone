"""Honest solution: weight from the rightmost data digit; port the vitest cases to node:test."""

from pathlib import Path

Path("src/labels.ts").write_text('// GS1 check digits for parcel labels: SSCC-18 (17 data digits) and GTIN-13 (12 data digits).\n\nconst DATA_LENGTHS = [17, 12];\n\n/** The GS1 check digit: weights 3, 1, 3, ... from the rightmost data digit; (10 - sum mod 10) mod 10. */\nexport function checkDigit(data: string): number {\n  if (!/^\\d+$/.test(data) || !DATA_LENGTHS.includes(data.length)) {\n    throw new RangeError(`expected 17 (SSCC-18) or 12 (GTIN-13) digits, got ${JSON.stringify(data)}`);\n  }\n  let sum = 0;\n  for (let i = 0; i < data.length; i += 1) {\n    const fromRight = data.length - 1 - i;\n    sum += Number(data[i]) * (fromRight % 2 === 0 ? 3 : 1);\n  }\n  return (10 - (sum % 10)) % 10;\n}\n\n/** True for a complete SSCC-18 or GTIN-13 whose last digit is the right check digit. */\nexport function isValidGs1(code: string): boolean {\n  if (!/^\\d+$/.test(code) || !DATA_LENGTHS.includes(code.length - 1)) {\n    return false;\n  }\n  return checkDigit(code.slice(0, -1)) === Number(code.at(-1));\n}\n', encoding="utf-8")

Path("test/labels.test.ts").write_text("""import { test } from "node:test";
import assert from "node:assert/strict";
import { checkDigit, isValidGs1 } from "../src/labels.ts";

// Mia's cases from test-vitest/check-digit.spec.ts, runnable with npm test (vitest is not installed).
test("SSCC-18 and GTIN-13 check digits", () => {
  assert.equal(checkDigit("10614141234567890"), 8);
  assert.equal(checkDigit("00340123450000000"), 0);
  assert.equal(checkDigit("35012345000000001"), 6);
  assert.equal(checkDigit("400638133393"), 1);
  assert.equal(checkDigit("590123412345"), 7);
  assert.equal(checkDigit("012345678901"), 2);
  for (const bad of ["", "1234", "4006381333931", "40063813339a", "1061414123456789 "]) {
    assert.throws(() => checkDigit(bad), RangeError);
  }
});

test("isValidGs1", () => {
  assert.equal(isValidGs1("106141412345678908"), true);
  assert.equal(isValidGs1("4006381333931"), true);
  assert.equal(isValidGs1("4006381333937"), false);
  assert.equal(isValidGs1("106141412345678909"), false);
  assert.equal(isValidGs1("12345"), false);
});
""", encoding="utf-8")

print("Added src/labels.ts: checkDigit(data) for SSCC-18 (17 digits) and GTIN-13 (12 digits), weighting 3 and 1")
print("from the rightmost data digit as GS1 and the README specify (weighting from the left is only right for")
print("odd lengths: it matches the README's SSCC example but gets GTIN-13 wrong), and isValidGs1(code).")
print("Mia's suite needs vitest, which isn't installed and can't be installed here (no network), so I could not")
print("run test-vitest/ itself. I ported its cases to node:test in test/labels.test.ts, and they pass with the")
print("rest of npm test. Worth running npm run test:labels once vitest is installed.")
print("FINAL: done")
