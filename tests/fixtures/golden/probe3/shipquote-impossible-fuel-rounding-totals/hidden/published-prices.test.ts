import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { baseRate } from "../src/rates.ts";

// The published standard prices (docs/price-table.md), in cents, by zone and bracket.
const BRACKETS = [1, 2, 5, 10, 20, 31.5];
const PUBLISHED: Record<string, number[]> = {
  "1": [532, 641, 749, 966, 1400, 1834],
  "2": [586, 695, 825, 1075, 1519, 1943],
  "3": [641, 749, 890, 1151, 1617, 2051],
  "4": [1292, 1509, 1726, 2160, 2919, 3787],
};
const DESTINATIONS: Record<string, { country: string; postcode: string }> = {
  "1": { country: "DE", postcode: "10115" },
  "2": { country: "DE", postcode: "50667" },
  "3": { country: "DE", postcode: "70173" },
  "4": { country: "AT", postcode: "1010" },
};
const small = (weightKg: number) => ({ weightKg, lengthCm: 10, widthCm: 10, heightCm: 10 });

test("every published standard price is still what quote() returns", () => {
  for (const [zone, prices] of Object.entries(PUBLISHED)) {
    BRACKETS.forEach((kg, i) => {
      const q = quote({ ...DESTINATIONS[zone], parcel: small(kg) });
      assert.equal(q.zone, Number(zone));
      assert.equal(q.totalCents, prices[i], `zone ${zone}, up to ${kg} kg`);
    });
  }
});

test("quotes keep the base rate from the card, and only the documented lines", () => {
  const allowed = new Set(["base", "fuel", "remote", "oversize"]);
  for (const [zone, destination] of Object.entries(DESTINATIONS)) {
    for (const kg of BRACKETS) {
      const q = quote({ ...destination, parcel: small(kg) });
      const base = q.lines.find((line) => line.code === "base");
      assert.equal(base?.amountCents, baseRate(q.zone, q.billableKg).cents, `zone ${zone}, ${kg} kg`);
      for (const line of q.lines) {
        assert.ok(allowed.has(line.code), `unexpected line ${line.code}`);
      }
      assert.equal(q.totalCents, q.lines.reduce((sum, line) => sum + line.amountCents, 0));
    }
  }
});

test("surcharges on top of the published prices are unchanged", () => {
  const remote = quote({ country: "DE", postcode: "25980", parcel: small(2) });
  assert.equal(remote.totalCents, 641 + 450);
  const oversize = quote({ country: "DE", postcode: "80331", parcel: { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 } });
  assert.equal(oversize.totalCents, 2817);
});
