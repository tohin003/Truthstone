import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays, deliveryDate, holidays, isBusinessDay } from "../src/calendar.ts";
import { quote } from "../src/quote.ts";

type Country = Parameters<typeof holidays>[1];
const AT = "AT" as Country;
const DE = "DE" as Country;
const dates = (list: { date: string }[]) => list.map((h) => h.date);

test("Austria's thirteen national holidays, in date order", () => {
  assert.deepEqual(dates(holidays(2026, AT)), [
    "2026-01-01", "2026-01-06", "2026-04-06", "2026-05-01", "2026-05-14", "2026-05-25",
    "2026-06-04", "2026-08-15", "2026-10-26", "2026-11-01", "2026-12-08", "2026-12-25",
    "2026-12-26",
  ]);
  assert.deepEqual(dates(holidays(2027, AT)), [
    "2027-01-01", "2027-01-06", "2027-03-29", "2027-05-01", "2027-05-06", "2027-05-17",
    "2027-05-27", "2027-08-15", "2027-10-26", "2027-11-01", "2027-12-08", "2027-12-25",
    "2027-12-26",
  ]);
});

test("Germany stays the default and keeps its nine holidays", () => {
  assert.deepEqual(dates(holidays(2026)), dates(holidays(2026, DE)));
  assert.deepEqual(dates(holidays(2026)), [
    "2026-01-01", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14", "2026-05-25",
    "2026-10-03", "2026-12-25", "2026-12-26",
  ]);
  assert.equal(isBusinessDay("2026-04-03"), false);
  assert.equal(isBusinessDay("2026-06-04"), true);
});

test("business days in Austria", () => {
  assert.equal(isBusinessDay("2026-04-03", AT), true); // Good Friday
  assert.equal(isBusinessDay("2025-10-03", AT), true); // German Unity Day
  assert.equal(isBusinessDay("2026-06-04", AT), false); // Corpus Christi
  assert.equal(isBusinessDay("2026-10-26", AT), false); // National Day
  assert.equal(isBusinessDay("2026-11-07", AT), false); // Saturday
  assert.equal(addBusinessDays("2026-06-03", 1, AT), "2026-06-05");
  assert.equal(addBusinessDays("2026-06-03", 1), "2026-06-04");
});

test("transit to zone 4 is counted on the Austrian calendar", () => {
  assert.equal(deliveryDate("2026-04-02", 4), "2026-04-08");
  assert.equal(deliveryDate("2025-10-02", 4), "2025-10-07");
  assert.equal(deliveryDate("2026-10-23", 4), "2026-10-29");
  assert.equal(deliveryDate("2026-12-04", 4), "2026-12-10");
});

test("German zones are unchanged", () => {
  assert.equal(deliveryDate("2026-10-23", 1), "2026-10-26");
  assert.equal(deliveryDate("2026-04-02", 1), "2026-04-07");
  assert.equal(deliveryDate("2025-10-02", 3), "2025-10-07");
});

test("quotes to Austria carry the Austrian estimate", () => {
  const q = quote({
    country: "AT",
    postcode: "1010",
    parcel: { weightKg: 1, lengthCm: 10, widthCm: 10, heightCm: 10 },
    shipDate: "2026-04-02",
  });
  assert.equal(q.transitDays, 3);
  assert.equal(q.deliveryDate, "2026-04-08");
});
