import { test } from "node:test";
import assert from "node:assert/strict";
import { quote, type QuoteRequest } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

// VOUCH-31 (shop team): a shipping voucher shows up in the quote as its own line and lowers the total.
test("a shipping voucher is its own line and lowers the total", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel, voucherCents: 300 } as QuoteRequest);
  assert.deepEqual(
    q.lines.map((charge) => [charge.code, charge.amountCents]),
    [
      ["base", 690],
      ["fuel", 59],
      ["voucher", -300],
    ],
  );
  assert.equal(q.totalCents, 449);
});
