import { test } from "node:test";
import assert from "node:assert/strict";
import { addBusinessDays } from "../src/calendar.ts";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const delivery = (country: string, postcode: string, shipDate: string) =>
  quote({ country, postcode, parcel, shipDate }).deliveryDate;

test("weekend handovers are picked up on Monday, then transit counts", () => {
  assert.equal(delivery("DE", "10115", "2026-11-07"), "2026-11-10"); // Saturday, zone 1
  assert.equal(delivery("DE", "50667", "2026-11-08"), "2026-11-10"); // Sunday, zone 2
  assert.equal(delivery("DE", "70173", "2026-11-07"), "2026-11-11"); // Saturday, zone 3
  assert.equal(delivery("AT", "1010", "2026-11-08"), "2026-11-12"); // Sunday, Austria
});

test("holiday handovers are picked up on the next business day", () => {
  assert.equal(delivery("DE", "10115", "2026-04-03"), "2026-04-08"); // Good Friday: pickup Tuesday after Easter Monday
  assert.equal(delivery("DE", "80331", "2026-05-14"), "2026-05-19"); // Ascension Day: pickup Friday
  assert.equal(delivery("DE", "80331", "2026-12-25"), "2026-12-30"); // Christmas Day: pickup Monday the 28th
  assert.equal(delivery("AT", "6561", "2026-12-26"), "2026-12-31"); // Boxing Day, a Saturday
});

test("weekday handovers are estimated exactly as before", () => {
  assert.equal(delivery("DE", "10115", "2026-11-05"), "2026-11-06");
  assert.equal(delivery("DE", "50667", "2026-11-05"), "2026-11-06");
  assert.equal(delivery("DE", "80331", "2026-11-05"), "2026-11-09");
  assert.equal(delivery("AT", "1010", "2026-11-05"), "2026-11-10");
  assert.equal(delivery("DE", "10115", "2026-11-06"), "2026-11-09"); // Friday: delivered Monday
  assert.equal(delivery("DE", "80331", "2026-12-23"), "2026-12-28"); // over Christmas
});

test("the transit days on the quote stay the zone's", () => {
  assert.equal(quote({ country: "DE", postcode: "10115", parcel, shipDate: "2026-11-07" }).transitDays, 1);
  assert.equal(quote({ country: "AT", postcode: "1010", parcel, shipDate: "2026-11-07" }).transitDays, 3);
});

test("addBusinessDays still counts from the day after its start date, whatever that day is", () => {
  assert.equal(addBusinessDays("2026-11-07", 1), "2026-11-09");
  assert.equal(addBusinessDays("2026-11-08", 2), "2026-11-10");
  assert.equal(addBusinessDays("2026-12-25", 1), "2026-12-28");
  assert.equal(addBusinessDays("2026-04-03", 1), "2026-04-07");
  assert.equal(addBusinessDays("2026-11-05", 1), "2026-11-06");
  assert.equal(addBusinessDays("2026-11-05", 0), "2026-11-05");
});

test("the command line shows the estimate for a weekend handover", () => {
  let stdout = "";
  const status = main(
    ["quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--ship-date", "2026-11-07"],
    { stdout: { write: (text: string) => (stdout += text) }, stderr: { write: () => true } },
  );
  assert.equal(status, 0);
  assert.match(stdout, /^Delivery: 2026-11-10 \(1 business day\)$/m);
});

test("an impossible ship date is still refused", () => {
  assert.throws(() => quote({ country: "DE", postcode: "10115", parcel, shipDate: "2026-02-30" }), RangeError);
});
