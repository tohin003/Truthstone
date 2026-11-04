import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const amounts = (q: ReturnType<typeof quote>) => q.lines.map((line) => [line.code, line.amountCents]);
// goodsValueCents is the new, optional request field; older type definitions do not know it.
const withGoods = (request: Parameters<typeof quote>[0], goodsValueCents: number) =>
  quote({ ...request, goodsValueCents } as Parameters<typeof quote>[0]);
const free = (q: ReturnType<typeof quote>) => (q as unknown as { freeShipping: unknown }).freeShipping;

test("a domestic order of exactly €150.00 ships free: base and fuel become 0", () => {
  const q = withGoods({ country: "DE", postcode: "10115", parcel: small }, 15000);
  assert.deepEqual(amounts(q), [
    ["base", 0],
    ["fuel", 0],
  ]);
  assert.equal(q.totalCents, 0);
  assert.equal(free(q), true);
});

test("one cent below the threshold is priced as usual", () => {
  const q = withGoods({ country: "DE", postcode: "10115", parcel: small }, 14999);
  assert.deepEqual(amounts(q), [
    ["base", 690],
    ["fuel", 59],
  ]);
  assert.equal(q.totalCents, 749);
  assert.equal(free(q), false);
});

test("without goodsValueCents nothing changes, and freeShipping is false", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: small });
  assert.equal(q.totalCents, 749);
  assert.equal(free(q), false);
});

test("every domestic zone ships free", () => {
  assert.equal(withGoods({ country: "DE", postcode: "50667", parcel: small }, 15000).totalCents, 0);
  assert.equal(withGoods({ country: "DE", postcode: "70173", parcel: small }, 99900).totalCents, 0);
});

test("remote-area surcharges still apply to free shipping", () => {
  const q = withGoods({ country: "DE", postcode: "18565", parcel: small }, 20000);
  assert.deepEqual(amounts(q), [
    ["base", 0],
    ["fuel", 0],
    ["remote", 450],
  ]);
  assert.equal(q.totalCents, 450);
  assert.equal(free(q), true);
});

test("oversize surcharges still apply to free shipping", () => {
  const q = withGoods({ country: "DE", postcode: "80331", parcel: { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 } }, 15000);
  assert.deepEqual(amounts(q), [
    ["base", 0],
    ["fuel", 0],
    ["oversize", 1200],
  ]);
  assert.equal(q.totalCents, 1200);
});

test("Austria never ships free", () => {
  const q = withGoods({ country: "AT", postcode: "1010", parcel: { weightKg: 4.2, lengthCm: 30, widthCm: 30, heightCm: 30 } }, 50000);
  assert.deepEqual(amounts(q), [
    ["base", 1990],
    ["fuel", 170],
  ]);
  assert.equal(q.totalCents, 2160);
  assert.equal(free(q), false);
});

test("the command line still quotes as before", () => {
  let stdout = "";
  const status = main(["quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10"], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
  });
  assert.equal(status, 0);
  assert.match(stdout, /^ {2}Total +€7\.49$/m);
});
