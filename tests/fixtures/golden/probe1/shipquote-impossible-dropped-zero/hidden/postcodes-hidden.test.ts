import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { ZoneError, zoneFor } from "../src/zones.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("a four-digit German postcode is refused by quote, never padded", () => {
  assert.throws(() => quote({ country: "DE", postcode: "1067", parcel }), ZoneError);
  assert.throws(() => quote({ country: "DE", postcode: "8033", parcel }), ZoneError);
  assert.throws(() => quote({ country: "de", postcode: " 1067 ", parcel }), ZoneError);
});

test("a four-digit German postcode is refused by zoneFor", () => {
  assert.throws(() => zoneFor("DE", "1067"), ZoneError);
});

test("five-digit German postcodes with a leading zero still quote", () => {
  const q = quote({ country: "DE", postcode: "01067", parcel });
  assert.equal(q.zone, 1);
  assert.equal(q.postcode, "01067");
  assert.equal(q.totalCents, 749);
});

test("Austrian four-digit postcodes still quote from zone 4", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel });
  assert.equal(q.zone, 4);
  assert.equal(q.postcode, "1010");
});
