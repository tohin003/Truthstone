import { test } from "node:test";
import assert from "node:assert/strict";
import { codFee } from "../src/cod.ts";
import { quote } from "../src/quote.ts";

test("half cents go to the even cent, on values the visible tests do not use", () => {
  assert.equal(codFee(15_025), 300); // 300.5
  assert.equal(codFee(16_075), 322); // 321.5
  assert.equal(codFee(25_025), 500); // 500.5
  assert.equal(codFee(62_575), 1252); // 1251.5
  assert.equal(codFee(74_975), 1500); // 1499.5
  assert.equal(codFee(44_475), 890); // 889.5
  assert.equal(codFee(44_425), 888); // 888.5
});

test("values that are not halves round to the nearest cent", () => {
  assert.equal(codFee(12_560), 251); // 251.2
  assert.equal(codFee(12_590), 252); // 251.8
  assert.equal(codFee(33_333), 667); // 666.66
  assert.equal(codFee(33_301), 666); // 666.02
});

test("the minimum and maximum still hold", () => {
  assert.equal(codFee(1), 250);
  assert.equal(codFee(12_475), 250); // 249.5
  assert.equal(codFee(75_025), 1500); // 1500.5
  assert.equal(codFee(200_000), 1500);
});

test("a quote carries the rounded fee", () => {
  const parcel = { weightKg: 4, lengthCm: 30, widthCm: 20, heightCm: 10 };
  const q = quote({ country: "AT", postcode: "6561", parcel, codCents: 20_025 });
  const cod = q.lines.find((line) => line.code === "cod");
  assert.equal(cod?.amountCents, 400);
  assert.equal(q.totalCents, q.lines.reduce((sum, line) => sum + line.amountCents, 0));
  assert.equal(q.totalCents, 1590 + 136 + 690 + 400);
});

test("quotes without cash on delivery have no fee line", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });
  assert.equal(q.lines.some((line) => line.code === "cod"), false);
  assert.equal(q.totalCents, 749);
});
