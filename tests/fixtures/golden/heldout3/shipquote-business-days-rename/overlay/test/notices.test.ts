import { test } from "node:test";
import assert from "node:assert/strict";
import { fill, NOTICES, renderNotice } from "../src/notices.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("the quote summary names the destination, the zone, the total and the billable weight", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel });
  assert.equal(renderNotice("quote-summary", q), "Shipping to DE 10115 (Germany North & East): €7.49, billed at 2.5 kg.\n");
});

test("a placeholder the quote has no value for renders empty", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel });
  assert.equal(fill("[{country}] [{zoneName}] [{nothing}]", q), "[AT] [Austria] []");
});

test("every notice has a template, and unknown notices are refused", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel, shipDate: "2026-11-05" });
  for (const name of NOTICES) {
    assert.ok(renderNotice(name, q).endsWith("\n"), name);
  }
  assert.throws(() => renderNotice("invoice" as never, q), RangeError);
});
