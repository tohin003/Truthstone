import { test } from "node:test";
import assert from "node:assert/strict";
import { isOversize, oversizeExcess, oversizeSurcharge } from "../src/surcharges.ts";
import { quote } from "../src/quote.ts";

const box = (lengthCm: number, widthCm: number, heightCm: number) => ({ weightKg: 1, lengthCm, widthCm, heightCm });

const orders = (a: number, b: number, c: number) => [box(a, b, c), box(a, c, b), box(b, a, c), box(b, c, a), box(c, a, b), box(c, b, a)];

test("the longest side decides, in every order of the same three sides", () => {
  for (const parcel of orders(125, 20, 10)) {
    assert.equal(isOversize(parcel), true, JSON.stringify(parcel));
    assert.deepEqual(oversizeExcess(parcel), { longestCm: 5, lengthPlusGirthCm: 0 });
  }
});

test("length plus girth is the longest side plus twice each other side, in every order", () => {
  for (const parcel of orders(100, 50, 40)) { // 100 + 100 + 80 = 280
    assert.equal(isOversize(parcel), false, JSON.stringify(parcel));
    assert.deepEqual(oversizeExcess(parcel), { longestCm: 0, lengthPlusGirthCm: 0 });
  }
  for (const parcel of orders(110, 60, 50)) { // 110 + 120 + 100 = 330
    assert.equal(isOversize(parcel), true, JSON.stringify(parcel));
    assert.deepEqual(oversizeExcess(parcel), { longestCm: 0, lengthPlusGirthCm: 30 });
  }
});

test("both limits can be exceeded at once, and the edges are not oversize", () => {
  assert.deepEqual(oversizeExcess(box(40, 140, 60)), { longestCm: 20, lengthPlusGirthCm: 40 }); // 140 + 120 + 80
  assert.equal(isOversize(box(10, 120, 10)), false);
  assert.equal(isOversize(box(50, 50, 100)), false); // exactly 300
  assert.equal(oversizeSurcharge(box(30, 20, 130)), 1200);
});

test("a quote for a parcel given short side first still carries the oversize line", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 4, lengthCm: 15, widthCm: 20, heightCm: 125 } });
  assert.ok(q.lines.some((line) => line.code === "oversize" && line.amountCents === 1200), JSON.stringify(q.lines));
});
