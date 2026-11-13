import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays, deliveryDate, easterSunday, holidays, isBusinessDay } from "../src/calendar.ts";

// Reference: the Meeus/Jones/Butcher Gregorian computus, written out independently.
function referenceEaster(year: number): string {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const h = (19 * a + b - Math.floor(b / 4) - Math.floor((b - Math.floor((b + 8) / 25) + 1) / 3) + 15) % 30;
  const l = (32 + 2 * (b % 4) + 2 * Math.floor(c / 4) - h - (c % 4)) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

test("Easter Sunday matches the Gregorian computus for every year 1900-2199", () => {
  for (let year = 1900; year < 2200; year += 1) {
    assert.equal(easterSunday(year), referenceEaster(year), String(year));
  }
});

test("the published Easter dates, exception years included", () => {
  assert.equal(easterSunday(1954), "1954-04-18");
  assert.equal(easterSunday(1981), "1981-04-19");
  assert.equal(easterSunday(2000), "2000-04-23");
  assert.equal(easterSunday(2026), "2026-04-05");
  assert.equal(easterSunday(2049), "2049-04-18");
  assert.equal(easterSunday(2076), "2076-04-19");
});

test("the 2049 holidays follow the right Easter", () => {
  assert.deepEqual(
    holidays(2049).map((holiday) => holiday.date),
    [
      "2049-01-01",
      "2049-04-16",
      "2049-04-19",
      "2049-05-01",
      "2049-05-27",
      "2049-06-07",
      "2049-10-03",
      "2049-12-25",
      "2049-12-26",
    ],
  );
  assert.equal(isBusinessDay("2049-04-16"), false); // Good Friday
  assert.equal(isBusinessDay("2049-04-23"), true);
});

test("delivery estimates over Easter 2049 skip Good Friday and Easter Monday", () => {
  assert.equal(addBusinessDays("2049-04-15", 1), "2049-04-20");
  assert.equal(deliveryDate("2049-04-15", 3), "2049-04-21");
});

test("the 2026 holidays are unchanged", () => {
  assert.deepEqual(
    holidays(2026).map((holiday) => holiday.date),
    ["2026-01-01", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14", "2026-05-25", "2026-10-03", "2026-12-25", "2026-12-26"],
  );
});
