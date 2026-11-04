import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";
import { deliveryDate } from "../src/calendar.ts";
import { quote } from "../src/quote.ts";
import { baseRate, rateCard } from "../src/rates.ts";
import { ZONE_NAMES, ZONES, zoneFor } from "../src/zones.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
type AnyZone = Parameters<typeof deliveryDate>[1];
const code = (value: string) => value as unknown as AnyZone;
const lines = (q: ReturnType<typeof quote>) => q.lines.map((line) => [line.code, line.amountCents]);

function cli(...argv: string[]) {
  let stdout = "";
  const status = main(argv, { stdout: { write: (text: string) => (stdout += text) }, stderr: { write: () => true } });
  return { status, stdout };
}

test("zoneFor returns zone codes", () => {
  assert.equal(zoneFor("DE", "10115"), "DE-1");
  assert.equal(zoneFor("DE", "01067"), "DE-1");
  assert.equal(zoneFor("DE", "50667"), "DE-2");
  assert.equal(zoneFor("DE", "80331"), "DE-3");
  assert.equal(zoneFor("AT", "1010"), "AT-1");
});

test("every zone is a code with a display name", () => {
  assert.deepEqual([...ZONES], ["DE-1", "DE-2", "DE-3", "AT-1"]);
  for (const zone of ZONES) {
    assert.equal(typeof ZONE_NAMES[zone], "string", zone);
  }
});

test("the rate card is keyed by zone code, with no numeric fallback", () => {
  assert.deepEqual(Object.keys(rateCard().zones).sort(), ["AT-1", "DE-1", "DE-2", "DE-3"]);
  assert.deepEqual(baseRate(code("DE-2"), 5), { cents: 760, bracketKg: 5 });
  assert.deepEqual(baseRate(code("AT-1"), 10), { cents: 1990, bracketKg: 10 });
  assert.throws(() => baseRate(1 as unknown as AnyZone, 5));
});

test("quotes are priced as before and carry the code", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: small });
  assert.equal(q.zone, "DE-1");
  assert.equal(q.totalCents, 749);
  assert.match(q.lines[0].label, /DE-1/);
  assert.equal(quote({ country: "AT", postcode: "1010", parcel: { weightKg: 4.2, lengthCm: 30, widthCm: 30, heightCm: 30 } }).totalCents, 2160);
});

test("remote-area surcharges still apply in every zone that has them", () => {
  assert.deepEqual(lines(quote({ country: "DE", postcode: "18565", parcel: small })), [["base", 690], ["fuel", 59], ["remote", 450]]);
  assert.deepEqual(lines(quote({ country: "DE", postcode: "87561", parcel: small })), [["base", 820], ["fuel", 70], ["remote", 350]]);
  assert.deepEqual(lines(quote({ country: "AT", postcode: "6561", parcel: small })), [["base", 1590], ["fuel", 136], ["remote", 690]]);
});

test("delivery estimates use each zone's transit days", () => {
  assert.equal(deliveryDate("2026-11-05", code("DE-1")), "2026-11-06");
  assert.equal(deliveryDate("2026-11-05", code("DE-3")), "2026-11-09");
  assert.equal(deliveryDate("2026-11-05", code("AT-1")), "2026-11-10");
  const q = quote({ country: "DE", postcode: "80331", parcel: small, shipDate: "2026-11-05" });
  assert.equal(q.transitDays, 2);
  assert.equal(q.deliveryDate, "2026-11-09");
});

test("the CLI lists the zones by code", () => {
  const { status, stdout } = cli("zones");
  assert.equal(status, 0);
  const listed = stdout.trimEnd().split("\n");
  assert.equal(listed.length, 4);
  assert.match(listed[0], /^zone DE-1 +Germany North & East +DE 0xxxx-2xxxx$/);
  assert.match(listed[3], /^zone AT-1 +Austria +AT/);
  assert.doesNotMatch(stdout, /undefined/);
});

test("the CLI quote names the zone code", () => {
  const { status, stdout } = cli("quote", "--country", "AT", "--postcode", "6561", "--weight", "2.3", "--dims", "20x15x10", "--ship-date", "2026-11-05");
  assert.equal(status, 0);
  assert.match(stdout, /^To AT 6561 \(zone AT-1\), billable weight 2\.5 kg$/m);
  assert.match(stdout, /^ {2}Remote area surcharge +€6\.90$/m);
  assert.match(stdout, /^Delivery: 2026-11-10 \(3 business days\)$/m);
});
