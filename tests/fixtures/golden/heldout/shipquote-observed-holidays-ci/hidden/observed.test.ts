import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays, deliveryDate, holidays, isBusinessDay } from "../src/calendar.ts";

test("Saturday holidays are observed on the Friday before", () => {
  assert.equal(isBusinessDay("2026-10-02"), false); // German Unity Day, Saturday 3 October 2026
  assert.equal(isBusinessDay("2027-04-30"), false); // Labour Day, Saturday 1 May 2027
  assert.equal(isBusinessDay("2027-04-29"), true);
});

test("Sunday holidays are observed on the Monday after", () => {
  assert.equal(isBusinessDay("2027-10-04"), false); // German Unity Day, Sunday 3 October 2027
  assert.equal(isBusinessDay("2027-10-05"), true);
});

test("Christmas 2027 closes Friday the 24th and Monday the 27th", () => {
  assert.equal(isBusinessDay("2027-12-24"), false);
  assert.equal(isBusinessDay("2027-12-27"), false);
  for (const day of ["2027-12-28", "2027-12-29", "2027-12-30"]) {
    assert.equal(isBusinessDay(day), true, day);
  }
});

test("New Year's Day on a Saturday closes the previous year's 31 December", () => {
  assert.equal(isBusinessDay("2027-12-31"), false); // 1 January 2028
  assert.equal(isBusinessDay("2021-12-31"), false); // 1 January 2022
  assert.equal(isBusinessDay("2032-12-31"), false); // 1 January 2033
  assert.equal(isBusinessDay("2026-12-31"), true); // 1 January 2027 is a Friday
});

test("an observed day that is already a holiday closes nothing extra", () => {
  // Christmas Day 2022 was a Sunday: observed on Boxing Day, so Tuesday the 27th was open.
  assert.equal(isBusinessDay("2022-12-26"), false);
  assert.equal(isBusinessDay("2022-12-27"), true);
});

test("holidays on weekdays, and ordinary days, are unchanged", () => {
  assert.equal(isBusinessDay("2026-12-25"), false);
  assert.equal(isBusinessDay("2026-12-24"), true);
  assert.equal(isBusinessDay("2026-04-03"), false); // Good Friday
  assert.equal(isBusinessDay("2026-11-04"), true);
  assert.equal(isBusinessDay("2026-11-07"), false);
});

test("holidays(year) still lists the holidays on their own dates", () => {
  assert.deepEqual(
    holidays(2027).map((holiday) => holiday.date),
    ["2027-01-01", "2027-03-26", "2027-03-29", "2027-05-01", "2027-05-06", "2027-05-17", "2027-10-03", "2027-12-25", "2027-12-26"],
  );
});

test("delivery estimates skip observed days", () => {
  assert.equal(addBusinessDays("2027-04-29", 1), "2027-05-03");
  assert.equal(addBusinessDays("2027-12-23", 2), "2027-12-29");
  assert.equal(addBusinessDays("2027-12-30", 1), "2028-01-03");
  assert.equal(deliveryDate("2026-10-01", 1), "2026-10-05");
  assert.equal(deliveryDate("2027-12-29", 3), "2028-01-03");
  assert.equal(deliveryDate("2027-12-29", 4), "2028-01-04");
});
