// 2027 quotes carry a 9.0% fuel surcharge (rounded up to the cent); 2026 quotes keep 8.5%.
import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});
const amounts = (q: ReturnType<typeof quote>) => Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("2027 quotes add 9% fuel, rounded up to the cent", () => {
  const small = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10), year: 2027 });
  assert.deepEqual(amounts(small), { base: 730, fuel: 66 }); // 65.7
  assert.equal(small.totalCents, 796);

  const heavy = quote({ country: "DE", postcode: "50667", parcel: box(18, 50, 40, 30), year: 2027 });
  assert.deepEqual(amounts(heavy), { base: 1470, fuel: 133 }); // 132.3
  assert.equal(heavy.totalCents, 1603);

  const austria = quote({ country: "AT", postcode: "1010", parcel: box(4.2, 30, 30, 30), year: 2027 });
  assert.deepEqual(amounts(austria), { base: 2090, fuel: 189 }); // 188.1
  assert.equal(austria.totalCents, 2279);
});

test("2026 quotes keep the 8.5% fuel surcharge", () => {
  const implicit = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  assert.deepEqual(amounts(implicit), { base: 690, fuel: 59 });
  assert.equal(implicit.totalCents, 749);
  const explicit = quote({ country: "DE", postcode: "50667", parcel: box(18, 50, 40, 30), year: 2026 });
  assert.deepEqual(amounts(explicit), { base: 1400, fuel: 119 });
});

test("a 2027 booking carries the 2027 fuel amount", () => {
  const body = bookingRequest(quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10), year: 2027 }), "ORD-1001");
  assert.equal(body.charges.find((charge) => charge.code === "fuel")?.amount, "0.66");
  assert.equal(body.total, "7.96");
});

test("the command line prices 2027 fuel too", () => {
  let stdout = "";
  const status = main(["quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--year", "2027", "--json"], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
  });
  assert.equal(status, 0);
  assert.equal(JSON.parse(stdout).totalCents, 796);
});
