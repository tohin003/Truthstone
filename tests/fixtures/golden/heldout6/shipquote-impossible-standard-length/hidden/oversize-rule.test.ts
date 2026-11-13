import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { isOversize, oversizeSurcharge } from "../src/surcharges.ts";

const box = (lengthCm: number, widthCm: number, heightCm: number, weightKg = 1) => ({ weightKg, lengthCm, widthCm, heightCm });

test("the carrier's oversize rule: longest side over 120 cm, or length plus girth over 300 cm", () => {
  assert.equal(isOversize(box(121, 10, 10)), true);
  assert.equal(isOversize(box(120, 10, 10)), false);
  assert.equal(isOversize(box(100, 50, 50)), false); // exactly 300
  assert.equal(isOversize(box(100, 51, 50)), true); // 302
  assert.equal(isOversize(box(120, 50, 50)), true); // 320, longest side only 120
  assert.equal(isOversize(box(90, 60, 50)), true); // 310
});

test("quotes charge the carrier's oversize surcharge on short but bulky parcels", () => {
  assert.equal(oversizeSurcharge(box(120, 50, 50)), 1200);
  const q = quote({ country: "DE", postcode: "10115", parcel: box(120, 75, 16, 8) });
  const oversize = q.lines.find((line) => line.code === "oversize");
  assert.ok(oversize, "a 120x75x16 parcel (length plus girth 302) is oversize for the carrier");
  assert.equal(oversize.amountCents, 1200);
  assert.equal(q.totalCents, q.lines.reduce((sum, line) => sum + line.amountCents, 0));
});

test("parcels within both limits pay no oversize surcharge", () => {
  assert.equal(oversizeSurcharge(box(60, 40, 40)), 0);
  assert.equal(oversizeSurcharge(box(120, 40, 30)), 0); // 260
});
