import { test } from "node:test";
import assert from "node:assert/strict";
import { codFee, CodError } from "../src/cod.ts";
import { quote } from "../src/quote.ts";
import { main } from "../src/cli.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("the cash-on-delivery fee is 2% of the goods value", () => {
  assert.equal(codFee(20_000), 400);
  assert.equal(codFee(50_000), 1000);
  assert.equal(codFee(31_260), 625); // 625.2
  assert.equal(codFee(31_290), 626); // 625.8
});

test("the fee is at least 2.50 and at most 15.00", () => {
  assert.equal(codFee(100), 250);
  assert.equal(codFee(12_000), 250);
  assert.equal(codFee(75_100), 1500);
  assert.equal(codFee(250_000), 1500);
});

test("exact half cents go to the even cent (contract 4.2)", () => {
  assert.equal(codFee(12_525), 250); // 250.5 -> 250
  assert.equal(codFee(13_775), 276); // 275.5 -> 276
  assert.equal(codFee(20_025), 400); // 400.5 -> 400
  assert.equal(codFee(30_075), 602); // 601.5 -> 602
});

test("goods values outside 0.01 to 2500.00 euros are refused", () => {
  assert.throws(() => codFee(0), CodError);
  assert.throws(() => codFee(250_001), CodError);
  assert.throws(() => codFee(10.5), RangeError);
});

test("a cash-on-delivery quote adds the fee as its own line", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel, codCents: 40_000 });
  assert.deepEqual(q.lines.at(-1), { code: "cod", label: "Cash on delivery fee", amountCents: 800 });
  assert.equal(q.totalCents, 690 + 59 + 800);
});

test("the fee on a half-cent goods value in a quote", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel, codCents: 40_025 });
  assert.equal(q.lines.at(-1)?.amountCents, 800); // 800.5 -> 800
  assert.equal(q.totalCents, 690 + 59 + 800);
});

test("--cod on the command line", () => {
  let stdout = "";
  const status = main(
    ["quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--cod", "400.00", "--json"],
    { stdout: { write: (text: string) => (stdout += text) }, stderr: { write: () => true } },
  );
  assert.equal(status, 0);
  assert.equal(JSON.parse(stdout).totalCents, 690 + 59 + 800);
});
