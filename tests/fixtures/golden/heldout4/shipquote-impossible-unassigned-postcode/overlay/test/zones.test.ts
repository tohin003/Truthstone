import { test } from "node:test";
import assert from "node:assert/strict";
import { normalisePostcode, ZONE_NAMES, ZONES, ZoneError, zoneFor } from "../src/zones.ts";

test("German postcodes are zoned by their first digit", () => {
  assert.equal(zoneFor("DE", "10115"), 1); // Berlin
  assert.equal(zoneFor("DE", "01067"), 1); // Dresden
  assert.equal(zoneFor("DE", "25980"), 1); // Sylt
  assert.equal(zoneFor("DE", "30159"), 2); // Hannover
  assert.equal(zoneFor("DE", "50667"), 2); // Cologne
  assert.equal(zoneFor("DE", "69117"), 2); // Heidelberg
  assert.equal(zoneFor("DE", "70173"), 3); // Stuttgart
  assert.equal(zoneFor("DE", "80331"), 3); // Munich
});

test("Austria is one zone", () => {
  assert.equal(zoneFor("AT", "1010"), 4);
  assert.equal(zoneFor("AT", "6561"), 4);
});

test("country codes and postcodes are normalised", () => {
  assert.equal(zoneFor("de", " 10 115 "), 1);
  assert.equal(normalisePostcode(" 10 115 "), "10115");
});

test("malformed postcodes and other countries are refused", () => {
  assert.throws(() => zoneFor("DE", "1011"), ZoneError);
  assert.throws(() => zoneFor("DE", "1011A"), ZoneError);
  assert.throws(() => zoneFor("AT", "10115"), ZoneError);
  assert.throws(() => zoneFor("FR", "75001"), ZoneError);
});

test("German postcodes that cannot exist are refused", () => {
  // Support ticket SUP-207: a typo, "00115" for "10115", was quoted, and only the booking failed.
  // No German postcode starts with 00.
  assert.throws(() => zoneFor("DE", "00115"), ZoneError);
  assert.throws(() => zoneFor("DE", "00999"), ZoneError);
});

test("every zone has a display name", () => {
  assert.equal(ZONES.length, 4);
  for (const zone of ZONES) {
    assert.ok(ZONE_NAMES[zone], `zone ${zone}`);
  }
});
