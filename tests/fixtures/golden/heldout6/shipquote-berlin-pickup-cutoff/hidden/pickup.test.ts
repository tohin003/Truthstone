import { test } from "node:test";
import assert from "node:assert/strict";
import { pickupDate } from "../src/index.ts";

test("before 14:00 Berlin time on a business day: picked up the same day", () => {
  assert.equal(pickupDate("2026-11-05T12:59:00Z"), "2026-11-05"); // 13:59 CET
  assert.equal(pickupDate("2026-11-05T07:00:00Z"), "2026-11-05");
});

test("at or after 14:00 Berlin time: the next business day", () => {
  assert.equal(pickupDate("2026-11-05T13:00:00Z"), "2026-11-06"); // 14:00 CET
  assert.equal(pickupDate("2026-11-06T15:00:00Z"), "2026-11-09"); // Friday 16:00 -> Monday
});

test("summer time: the cutoff is 12:00 UTC", () => {
  assert.equal(pickupDate("2026-07-01T11:59:00Z"), "2026-07-01"); // 13:59 CEST
  assert.equal(pickupDate("2026-07-01T12:30:00Z"), "2026-07-02"); // 14:30 CEST
  assert.equal(pickupDate("2026-03-30T12:30:00Z"), "2026-03-31"); // the Monday after the switch
  assert.equal(pickupDate("2026-10-23T12:30:00Z"), "2026-10-26"); // last Friday of summer time
  assert.equal(pickupDate("2026-10-26T12:30:00Z"), "2026-10-26"); // back on CET: 13:30
});

test("the Berlin calendar day counts, not the UTC one", () => {
  assert.equal(pickupDate("2026-11-05T23:30:00Z"), "2026-11-06"); // Friday 00:30 in Berlin
  assert.equal(pickupDate("2026-11-08T23:30:00Z"), "2026-11-09"); // Sunday in UTC, Monday in Berlin
});

test("weekends and holidays roll to the next business day", () => {
  assert.equal(pickupDate("2026-11-07T09:00:00Z"), "2026-11-09"); // Saturday
  assert.equal(pickupDate("2026-12-24T10:00:00Z"), "2026-12-24");
  assert.equal(pickupDate("2026-12-24T14:00:00Z"), "2026-12-28"); // Christmas, Boxing Day, Sunday
  assert.equal(pickupDate("2026-10-02T13:30:00Z"), "2026-10-05"); // Friday 15:30, German Unity Day is a Saturday
});

test("an explicit offset is honoured", () => {
  assert.equal(pickupDate("2026-11-05T14:30:00+01:00"), "2026-11-06");
  assert.equal(pickupDate("2026-11-05T08:30:00-05:00"), "2026-11-06"); // 14:30 in Berlin
  assert.equal(pickupDate("2026-11-05T15:30:00+03:00"), "2026-11-05"); // 13:30 in Berlin
});

test("a timestamp without Z or an offset is refused", () => {
  assert.throws(() => pickupDate("2026-11-05T13:30:00"), RangeError);
});

test("the rest of the public API is unchanged", async () => {
  const api = await import("../src/index.ts");
  for (const name of ["quote", "bookingRequest", "zoneFor", "deliveryDate", "addBusinessDays", "formatEUR"]) {
    assert.equal(typeof (api as Record<string, unknown>)[name], "function", name);
  }
});
