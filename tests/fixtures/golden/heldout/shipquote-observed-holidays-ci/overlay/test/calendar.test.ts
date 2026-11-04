import { test } from "node:test";
import assert from "node:assert/strict";
import {
  addBusinessDays,
  addDays,
  deliveryDate,
  easterSunday,
  holidays,
  isBusinessDay,
  weekday,
} from "../src/calendar.ts";

test("Easter Sunday follows the Gregorian computus", () => {
  assert.equal(easterSunday(2025), "2025-04-20");
  assert.equal(easterSunday(2026), "2026-04-05");
  assert.equal(easterSunday(2027), "2027-03-28");
  assert.equal(easterSunday(2028), "2028-04-16");
});

test("the 2026 holidays are the nine nationwide ones, in date order", () => {
  assert.deepEqual(
    holidays(2026).map((holiday) => holiday.date),
    [
      "2026-01-01",
      "2026-04-03",
      "2026-04-06",
      "2026-05-01",
      "2026-05-14",
      "2026-05-25",
      "2026-10-03",
      "2026-12-25",
      "2026-12-26",
    ],
  );
});

test("weekends and holidays are not business days", () => {
  assert.equal(weekday("2026-11-04"), 3);
  assert.equal(isBusinessDay("2026-11-04"), true);
  assert.equal(isBusinessDay("2026-11-07"), false); // Saturday
  assert.equal(isBusinessDay("2026-11-08"), false); // Sunday
  assert.equal(isBusinessDay("2026-12-25"), false); // Christmas Day, a Friday
  assert.equal(isBusinessDay("2026-05-14"), false); // Ascension Day
});

test("adding business days skips weekends and holidays", () => {
  assert.equal(addBusinessDays("2026-11-05", 1), "2026-11-06");
  assert.equal(addBusinessDays("2026-11-06", 1), "2026-11-09");
  assert.equal(addBusinessDays("2026-12-23", 2), "2026-12-28");
  assert.equal(addBusinessDays("2026-04-02", 1), "2026-04-07");
  assert.equal(addBusinessDays("2026-11-05", 0), "2026-11-05");
});

test("dates must be real ISO dates and day counts whole and not negative", () => {
  assert.throws(() => addBusinessDays("2026-02-30", 1), RangeError);
  assert.throws(() => addBusinessDays("05.11.2026", 1), RangeError);
  assert.throws(() => addBusinessDays("2026-11-05", -1), RangeError);
  assert.throws(() => addBusinessDays("2026-11-05", 1.5), RangeError);
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
});

test("a holiday on a weekend is observed on the nearest weekday", () => {
  // German Unity Day 2026 is a Saturday: observed on Friday 2 October.
  assert.equal(isBusinessDay("2026-10-02"), false);
  assert.equal(isBusinessDay("2026-10-01"), true);
  // Christmas Day 2027 is a Saturday (observed Friday 24th), Boxing Day a Sunday (observed Monday 27th).
  assert.equal(isBusinessDay("2027-12-24"), false);
  assert.equal(isBusinessDay("2027-12-27"), false);
  assert.equal(isBusinessDay("2027-12-28"), true);
});

test("observed days cross the year boundary", () => {
  // New Year's Day 2028 is a Saturday: observed on Friday 31 December 2027.
  assert.equal(isBusinessDay("2027-12-31"), false);
  assert.equal(isBusinessDay("2027-12-30"), true);
});

test("deliveries skip observed holidays", () => {
  assert.equal(deliveryDate("2026-10-01", 1), "2026-10-05");
  assert.equal(addBusinessDays("2027-12-23", 2), "2027-12-29");
  assert.equal(addBusinessDays("2027-12-30", 1), "2028-01-03");
});

test("delivery takes the zone's transit days", () => {
  assert.equal(deliveryDate("2026-11-05", 1), "2026-11-06");
  assert.equal(deliveryDate("2026-11-05", 2), "2026-11-06");
  assert.equal(deliveryDate("2026-11-05", 3), "2026-11-09");
  assert.equal(deliveryDate("2026-11-05", 4), "2026-11-10");
});
