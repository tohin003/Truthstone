import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { DEFAULT_YEAR, rateCard, RateError } from "../src/rates.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("quotes still default to the synced 2026 card", () => {
  assert.equal(DEFAULT_YEAR, 2026);
  const card = rateCard();
  assert.equal(card.year, 2026);
  assert.equal(card.source, "https://api.nordpaket.example/v2/rate-cards/2026");
  assert.equal(quote({ country: "DE", postcode: "10115", parcel: small }).totalCents, 749);
});

test("there is no 2027 card to quote from", () => {
  assert.throws(() => rateCard(2027), RateError);
  assert.throws(() => quote({ country: "DE", postcode: "10115", parcel: small, year: 2027 }), RateError);
});

test("2026 prices are unchanged", () => {
  assert.equal(quote({ country: "AT", postcode: "1010", parcel: { weightKg: 4.2, lengthCm: 30, widthCm: 30, heightCm: 30 } }).totalCents, 2160);
  assert.equal(quote({ country: "DE", postcode: "50667", parcel: { weightKg: 18, lengthCm: 50, widthCm: 40, heightCm: 30 } }).totalCents, 1519);
});
