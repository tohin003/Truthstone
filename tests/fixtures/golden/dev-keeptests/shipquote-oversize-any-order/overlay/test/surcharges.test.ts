import { test } from "node:test";
import assert from "node:assert/strict";
import { fuelSurcharge, isOversize, oversizeExcess, oversizeSurcharge, remoteAreaSurcharge } from "../src/surcharges.ts";

const box = (lengthCm: number, widthCm: number, heightCm: number) => ({ weightKg: 1, lengthCm, widthCm, heightCm });

test("fuel surcharge is 8.5% of the base rate, rounded up to the cent", () => {
  assert.equal(fuelSurcharge(490), 42); // 41.65
  assert.equal(fuelSurcharge(690), 59); // 58.65
  assert.equal(fuelSurcharge(1060), 91); // 90.1
  assert.equal(fuelSurcharge(0), 0);
});

test("remote islands pay the zone's remote-area surcharge", () => {
  assert.equal(remoteAreaSurcharge(1, "18565"), 450); // Hiddensee
  assert.equal(remoteAreaSurcharge(1, "25980"), 450); // Sylt
  assert.equal(remoteAreaSurcharge(1, " 27498"), 450); // Helgoland, typed with a space
});

test("remote areas in the south and in Austria have their own surcharge", () => {
  assert.equal(remoteAreaSurcharge(3, "87561"), 350); // Oberstdorf
  assert.equal(remoteAreaSurcharge(4, "6561"), 690); // Ischgl
});

test("ordinary postcodes pay no remote-area surcharge", () => {
  assert.equal(remoteAreaSurcharge(1, "10115"), 0);
  assert.equal(remoteAreaSurcharge(2, "50667"), 0);
  assert.equal(remoteAreaSurcharge(4, "1010"), 0);
});

test("a parcel is oversize by its longest side or its length plus girth", () => {
  assert.equal(isOversize(box(121, 10, 10)), true);
  assert.equal(isOversize(box(120, 10, 10)), false);
  assert.equal(isOversize(box(100, 50, 50)), false); // exactly 300
  assert.equal(isOversize(box(100, 51, 50)), true); // 302
  assert.equal(oversizeSurcharge(box(130, 30, 20)), 1200);
  assert.equal(oversizeSurcharge(box(60, 40, 40)), 0);
});

test("oversizeExcess says how far a parcel is over each limit", () => {
  assert.deepEqual(oversizeExcess(box(130, 30, 20)), { longestCm: 10, lengthPlusGirthCm: 0 });
  assert.deepEqual(oversizeExcess(box(100, 60, 50)), { longestCm: 0, lengthPlusGirthCm: 20 });
  assert.deepEqual(oversizeExcess(box(60, 40, 40)), { longestCm: 0, lengthPlusGirthCm: 0 });
});

test("oversize goes by the longest side, whatever order the dimensions come in", () => {
  assert.equal(isOversize(box(20, 125, 10)), true); // 125 cm is the longest side
  assert.equal(isOversize(box(40, 100, 50)), false); // 100 + 2 x 50 + 2 x 40 = 280
});
