import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LEGACY_YEARS, legacyBaseRate, legacyTable } from "../src/legacy-rates.ts";
import type { Zone } from "../src/zones.ts";

type OldQuote = { zone: Zone; weightKg: number; year: number; cents: number };

const OLD_QUOTES = JSON.parse(
  readFileSync(new URL("../fixtures/legacy/expected-quotes.json", import.meta.url), "utf8"),
) as OldQuote[];

test("legacy tables cover 2024 and 2025", () => {
  assert.deepEqual([...LEGACY_YEARS], [2024, 2025]);
  for (const year of LEGACY_YEARS) {
    assert.equal(legacyTable(year).year, year);
  }
});

test("legacy base rates match the quotes the old system gave", () => {
  for (const { zone, weightKg, year, cents } of OLD_QUOTES) {
    assert.equal(legacyBaseRate(zone, weightKg, year), cents, `zone ${zone}, ${weightKg} kg, ${year}`);
  }
});

test("years without a legacy table are errors", () => {
  assert.throws(() => legacyTable(2026), RangeError);
  assert.throws(() => legacyBaseRate(1, 2, 2023), RangeError);
});
