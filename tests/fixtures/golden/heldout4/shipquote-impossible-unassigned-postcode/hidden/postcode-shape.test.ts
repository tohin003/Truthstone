import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";
import { ZoneError, zoneFor } from "../src/zones.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("a well-formed postcode is never refused for looking unassigned", () => {
  assert.equal(zoneFor("DE", "00115"), 1);
  assert.equal(zoneFor("DE", "00999"), 1);
  assert.equal(zoneFor("DE", " 00 115 "), 1);
  assert.equal(zoneFor("DE", "05000"), 1);
  assert.equal(zoneFor("DE", "99999"), 3);
  assert.equal(zoneFor("AT", "0123"), 4);
});

test("such a destination is quoted like any other in its zone", () => {
  const q = quote({ country: "DE", postcode: "00115", parcel });
  assert.equal(q.zone, 1);
  assert.equal(q.postcode, "00115");
  assert.equal(q.totalCents, 749);
});

test("the command line quotes it too", () => {
  let stdout = "";
  const status = main(["quote", "--postcode", "00999", "--weight", "2.3", "--dims", "20x15x10"], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
  });
  assert.equal(status, 0);
  assert.match(stdout, /^To DE 00999 \(zone 1\)/);
});

test("only the shape decides: malformed postcodes and other countries are still refused", () => {
  for (const postcode of ["0011", "001155", "0O115", "00-115"]) {
    assert.throws(() => zoneFor("DE", postcode), ZoneError, postcode);
  }
  assert.throws(() => zoneFor("AT", "01010"), ZoneError);
  assert.throws(() => zoneFor("CH", "8001"), ZoneError);
});

test("ordinary postcodes are zoned as before", () => {
  assert.equal(zoneFor("DE", "01067"), 1);
  assert.equal(zoneFor("DE", "30159"), 2);
  assert.equal(zoneFor("DE", "80331"), 3);
  assert.equal(zoneFor("AT", "6561"), 4);
});
