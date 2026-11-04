// Legacy rates: the pre-1.3 per-kilogram tables, kept while checkout compared old and new quotes.
import { readFileSync } from "node:fs";
import type { Zone } from "./zones.ts";

/** The years the legacy tables cover. */
export const LEGACY_YEARS: readonly number[] = [2024, 2025];

export type LegacyTable = {
  year: number;
  /** Cents for the first kilogram, per zone. */
  firstKgCents: Record<string, number>;
  /** Cents for every further started kilogram, per zone. */
  perKgCents: Record<string, number>;
};

/** The legacy table for `year`, read from fixtures/legacy/rates-<year>.json. */
export function legacyTable(year: number): LegacyTable {
  if (!LEGACY_YEARS.includes(year)) {
    throw new RangeError(`no legacy table for ${year}`);
  }
  const url = new URL(`../fixtures/legacy/rates-${year}.json`, import.meta.url);
  return JSON.parse(readFileSync(url, "utf8")) as LegacyTable;
}

/** The pre-1.3 base rate in cents: the first kilogram, then every further started kilogram. */
export function legacyBaseRate(zone: Zone, weightKg: number, year: number = 2025): number {
  const table = legacyTable(year);
  const first = table.firstKgCents[String(zone)];
  const perKg = table.perKgCents[String(zone)];
  if (first === undefined || perKg === undefined) {
    throw new RangeError(`the ${year} legacy table has no zone ${zone}`);
  }
  return first + Math.max(0, Math.ceil(weightKg) - 1) * perKg;
}
