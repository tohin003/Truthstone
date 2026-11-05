import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays, deliveryDate, holidays, isBusinessDay } from "../src/index.ts";

test("24 and 31 December are not delivery days, in any year", () => {
  for (const day of ["2026-12-24", "2026-12-31", "2027-12-24", "2027-12-31", "2025-12-24"]) {
    assert.equal(isBusinessDay(day), false, day);
  }
  assert.equal(isBusinessDay("2026-12-23"), true);
  assert.equal(isBusinessDay("2026-12-29"), true);
  assert.equal(deliveryDate("2026-12-23", 1), "2026-12-28");
  assert.equal(deliveryDate("2026-12-30", 3), "2027-01-05");
  assert.equal(deliveryDate("2027-12-23", 2), "2027-12-27");
  assert.equal(addBusinessDays("2027-12-30", 1), "2028-01-03");
});

test("the public holidays are still the nine nationwide ones", () => {
  const dates = holidays(2026).map((holiday) => holiday.date);
  assert.equal(dates.length, 9);
  assert.ok(!dates.includes("2026-12-24") && !dates.includes("2026-12-31"));
  assert.deepEqual(holidays(2027).map((holiday) => holiday.name).slice(-2), ["Christmas Day", "Boxing Day"]);
});
