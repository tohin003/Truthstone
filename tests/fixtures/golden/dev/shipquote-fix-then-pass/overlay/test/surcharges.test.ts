import { test } from "node:test";
import assert from "node:assert/strict";
import { fuelSurcharge, isOversize, oversizeSurcharge, remoteAreaSurcharge } from "../src/surcharges.ts";

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

test("remote-area surcharge applies to postcodes with a leading zero", () => {
  assert.equal(remoteAreaSurcharge(1, "09484"), 450); // Oberwiesenthal
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
