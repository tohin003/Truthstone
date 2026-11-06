import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
type Request = Parameters<typeof quote>[0];
// orderedAt and pickupDate are new; older type definitions do not know them.
const ordered = (orderedAt: string, extra: Record<string, unknown> = {}, postcode = "10115") =>
  quote({ country: "DE", postcode, parcel, orderedAt, ...extra } as unknown as Request) as unknown as {
    pickupDate?: string;
    deliveryDate?: string;
    transitDays?: number;
    totalCents: number;
  };
const pickup = (orderedAt: string) => ordered(orderedAt).pickupDate;

test("winter (CET): before 14:00 Berlin time is picked up the same day", () => {
  assert.equal(pickup("2026-11-05T12:59:00Z"), "2026-11-05"); // Thu 13:59 CET
  assert.equal(pickup("2026-11-05T07:00:00Z"), "2026-11-05");
});

test("winter (CET): 14:00 Berlin time and later go to the next business day", () => {
  assert.equal(pickup("2026-11-05T13:00:00Z"), "2026-11-06"); // Thu 14:00 CET
  assert.equal(pickup("2026-11-05T12:30:00Z"), "2026-11-05"); // Thu 13:30 CET, though 12:30 UTC
  assert.equal(pickup("2026-11-06T13:30:00Z"), "2026-11-09"); // Fri 14:30 CET -> Monday
});

test("summer (CEST): the cut-off is 12:00 UTC", () => {
  assert.equal(pickup("2026-07-01T11:59:00Z"), "2026-07-01"); // Wed 13:59 CEST
  assert.equal(pickup("2026-07-01T12:00:00Z"), "2026-07-02"); // Wed 14:00 CEST
  assert.equal(pickup("2026-07-01T12:45:00Z"), "2026-07-02"); // 13:45 if it were CET: still too late
});

test("around the clock changes the offset follows the date", () => {
  assert.equal(pickup("2026-03-27T12:30:00Z"), "2026-03-27"); // Fri 13:30 CET, the last CET weekday
  assert.equal(pickup("2026-03-30T12:30:00Z"), "2026-03-31"); // Mon 14:30 CEST, the first CEST weekday
  assert.equal(pickup("2026-10-23T12:30:00Z"), "2026-10-26"); // Fri 14:30 CEST -> Monday
  assert.equal(pickup("2026-10-26T12:30:00Z"), "2026-10-26"); // Mon 13:30 CET
});

test("orders on weekends and public holidays are picked up on the next business day", () => {
  assert.equal(pickup("2026-11-07T09:00:00Z"), "2026-11-09"); // Saturday morning
  assert.equal(pickup("2026-11-08T22:00:00Z"), "2026-11-09"); // Sun 23:00 CET -> Monday
  assert.equal(pickup("2026-12-25T09:00:00Z"), "2026-12-28"); // Christmas Day (Fri), Boxing Day (Sat)
  assert.equal(pickup("2026-04-02T13:00:00Z"), "2026-04-07"); // Thu 15:00 CEST before Easter
});

test("just after midnight Berlin time counts for the Berlin day", () => {
  assert.equal(pickup("2026-11-05T23:30:00Z"), "2026-11-06"); // Fri 00:30 CET
  assert.equal(pickup("2026-07-02T22:30:00Z"), "2026-07-03"); // Fri 00:30 CEST
});

test("the delivery estimate counts from the pickup date", () => {
  const sameDay = ordered("2026-11-05T09:00:00Z"); // zone 1, picked up Thu
  assert.equal(sameDay.pickupDate, "2026-11-05");
  assert.equal(sameDay.deliveryDate, "2026-11-06");
  assert.equal(sameDay.transitDays, 1);
  const late = ordered("2026-11-06T15:00:00Z", {}, "80331"); // zone 3, Fri 16:00 CET -> Mon pickup
  assert.equal(late.pickupDate, "2026-11-09");
  assert.equal(late.deliveryDate, "2026-11-11");
  assert.equal(late.transitDays, 2);
  assert.equal(late.totalCents, quote({ country: "DE", postcode: "80331", parcel }).totalCents);
});

test("an explicit shipDate wins over orderedAt", () => {
  const q = ordered("2026-11-05T15:00:00Z", { shipDate: "2026-11-10" });
  assert.equal(q.deliveryDate, "2026-11-11");
});

test("without orderedAt or shipDate there is no estimate, as before", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel });
  assert.equal(q.deliveryDate, undefined);
  assert.equal(q.transitDays, undefined);
  assert.equal(q.totalCents, 749);
});

test("a shipDate alone still works as before", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel, shipDate: "2026-11-05" });
  assert.equal(q.deliveryDate, "2026-11-10");
});

test("an orderedAt that is not a timestamp is a RangeError", () => {
  for (const bad of ["yesterday", "2026-13-45T25:00:00Z"]) {
    assert.throws(() => ordered(bad), RangeError, bad);
  }
});
