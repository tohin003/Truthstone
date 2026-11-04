import { test } from "node:test";
import assert from "node:assert/strict";
import * as shipquote from "../src/index.ts";

// Every value the public API exported before the legacy rates were added.
const PUBLIC = [
  "DEFAULT_YEAR",
  "FUEL_RATE",
  "ParcelError",
  "RateError",
  "TRANSIT_DAYS",
  "ZONES",
  "ZONE_NAMES",
  "ZoneError",
  "addBusinessDays",
  "baseRate",
  "billableWeight",
  "bookingRequest",
  "deliveryDate",
  "formatAmount",
  "formatEUR",
  "holidays",
  "isBusinessDay",
  "isOversize",
  "parseEuros",
  "quote",
  "rateCard",
  "volumetricWeight",
  "zoneFor",
];

test("the public API no longer exports anything legacy", () => {
  assert.deepEqual(Object.keys(shipquote).filter((name) => /legacy/i.test(name)), []);
});

test("every other export is still there, and nothing was added", () => {
  assert.deepEqual(Object.keys(shipquote).sort(), [...PUBLIC].sort());
});

test("a quote through the public API is unchanged", () => {
  const q = shipquote.quote({
    country: "DE",
    postcode: "10115",
    parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 },
  });
  assert.equal(q.zone, 1);
  assert.equal(q.billableKg, 2.5);
  assert.equal(shipquote.formatEUR(q.totalCents), "€7.49");
});

test("the rate cards in data/ still load", () => {
  assert.equal(shipquote.DEFAULT_YEAR, 2026);
  assert.equal(shipquote.rateCard(2026).carrier, "Nordpaket");
  assert.deepEqual(shipquote.baseRate(1, 1.5), { cents: 590, bracketKg: 2 });
  assert.deepEqual(shipquote.baseRate(2, 20, 2026), { cents: 1400, bracketKg: 20 });
});
