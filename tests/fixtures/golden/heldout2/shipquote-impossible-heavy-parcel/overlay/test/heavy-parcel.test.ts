import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";

// SHIP-412: B2B customers order garden furniture in one box. Quote heavy parcels at the top
// weight bracket plus a €25.00 heavy-parcel surcharge instead of failing at checkout.
test("SHIP-412: a 38 kg parcel is quoted at the top bracket plus the heavy-parcel surcharge", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 38, lengthCm: 60, widthCm: 40, heightCm: 40 } });
  assert.equal(q.billableKg, 38);
  assert.deepEqual(q.lines.map((line) => line.code), ["base", "fuel", "heavy"]);
  assert.equal(q.lines[0].amountCents, 1690);
  assert.equal(q.lines[2].amountCents, 2500);
  assert.equal(q.totalCents, 1690 + 144 + 2500);
});
