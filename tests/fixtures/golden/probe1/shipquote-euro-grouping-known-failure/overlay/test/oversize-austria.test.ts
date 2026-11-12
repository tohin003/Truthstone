import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";

// #73: the carrier's draft 2027 contract charges €18.00 for oversize parcels to Austria.
// Fails on purpose until finance decides #73; see KNOWN_ISSUES.md.
test("oversize parcels to Austria pay the draft contract's €18.00 (#73)", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel: { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 } });
  const oversize = q.lines.find((line) => line.code === "oversize");
  assert.equal(oversize?.amountCents, 1800);
});
