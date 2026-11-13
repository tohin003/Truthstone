import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays, deliveryDate, holidays, isBusinessDay, weekday } from "../src/calendar.ts";

const dateOf = (year: number, name: string) => holidays(year).find((holiday) => holiday.name === name)?.date;

test("Whit Monday is the Monday after Pentecost, fifty days after Easter Sunday", () => {
  assert.equal(dateOf(2025, "Whit Monday"), "2025-06-09");
  assert.equal(dateOf(2026, "Whit Monday"), "2026-05-25");
  assert.equal(dateOf(2027, "Whit Monday"), "2027-05-17");
  assert.equal(dateOf(2028, "Whit Monday"), "2028-06-05");
  for (const year of [2025, 2026, 2027, 2028, 2029, 2030]) {
    const date = dateOf(year, "Whit Monday");
    assert.ok(date, `no Whit Monday in ${year}`);
    assert.equal(weekday(date), 1, `${year}: ${date} is not a Monday`);
  }
});

test("Whit Monday is not a business day and the Tuesday after it is", () => {
  assert.equal(isBusinessDay("2026-05-25"), false);
  assert.equal(isBusinessDay("2026-05-26"), true);
  assert.equal(isBusinessDay("2027-05-17"), false);
});

test("deliveries over the Whitsun weekend skip Whit Monday", () => {
  assert.equal(addBusinessDays("2026-05-22", 1), "2026-05-26");
  assert.equal(deliveryDate("2026-05-22", 3), "2026-05-27");
  assert.equal(deliveryDate("2027-05-14", 1), "2027-05-18");
});

test("each year still has exactly the nine nationwide holidays, the others unchanged", () => {
  for (const year of [2025, 2026, 2027]) {
    assert.equal(holidays(year).length, 9, String(year));
  }
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
  assert.equal(dateOf(2027, "Good Friday"), "2027-03-26");
  assert.equal(dateOf(2027, "Ascension Day"), "2027-05-06");
});
