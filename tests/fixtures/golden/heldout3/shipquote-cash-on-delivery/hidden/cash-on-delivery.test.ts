// Cash on delivery as the README specifies it: 3.5 % rounded up without float noise, €3.00-€15.00,
// a "cod" line with no fuel on it, amounts from €1.00 to €1,500.00 in whole cents, Germany only.
import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";
import { ZoneError } from "../src/zones.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
type Request = Parameters<typeof quote>[0];
const withCod = (codAmountCents: number, country = "DE", postcode = "10115", parcel = small) =>
  quote({ country, postcode, parcel, codAmountCents } as Request);
const amounts = (q: ReturnType<typeof quote>) =>
  Object.fromEntries(q.lines.map((line) => [line.code as string, line.amountCents]));

test("the fee is 3.5 % rounded up, and float noise never adds a cent", () => {
  const cases: Array<[number, number]> = [
    [10000, 350],
    [8600, 301],
    [9000, 315],
    [20000, 700],
    [12345, 433],
    [11111, 389],
    [30001, 1051],
  ];
  for (const [amount, fee] of cases) {
    assert.equal(amounts(withCod(amount)).cod, fee, `collecting ${amount}`);
  }
});

test("the fee is at least €3.00 and at most €15.00", () => {
  assert.equal(amounts(withCod(100)).cod, 300);
  assert.equal(amounts(withCod(5000)).cod, 300);
  assert.equal(amounts(withCod(8572)).cod, 301);
  assert.equal(amounts(withCod(42857)).cod, 1500);
  assert.equal(amounts(withCod(42858)).cod, 1500);
  assert.equal(amounts(withCod(150000)).cod, 1500);
});

test("the fee is its own line, labelled, with no fuel surcharge on it", () => {
  const q = withCod(10000);
  const line = q.lines.find((l) => (l.code as string) === "cod");
  assert.deepEqual(line, { code: "cod", label: "Cash on delivery", amountCents: 350 });
  assert.deepEqual(amounts(q), { base: 690, fuel: 59, cod: 350 });
  assert.equal(q.totalCents, 1099);
});

test("cash on delivery combines with the other surcharges", () => {
  const q = withCod(20000, "DE", "18565", { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 });
  assert.deepEqual(amounts(q), { base: 1290, fuel: 110, remote: 450, oversize: 1200, cod: 700 });
  assert.equal(q.totalCents, 1290 + 110 + 450 + 1200 + 700);
});

test("amounts outside €1.00-€1,500.00, or not whole cents, are refused", () => {
  for (const amount of [0, 99, 150001, -500, 1000.5, Number.NaN]) {
    assert.throws(() => withCod(amount), RangeError, String(amount));
  }
});

test("cash on delivery is Germany only", () => {
  assert.throws(() => withCod(10000, "AT", "1010"), ZoneError);
  for (const postcode of ["10115", "50667", "80331"]) {
    assert.equal(amounts(withCod(10000, "DE", postcode)).cod, 350, postcode);
  }
});

test("quotes without cash on delivery are unchanged", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: small });
  assert.deepEqual(amounts(q), { base: 690, fuel: 59 });
  assert.equal(q.totalCents, 749);
  const at = quote({ country: "AT", postcode: "1010", parcel: { weightKg: 4.2, lengthCm: 30, widthCm: 30, heightCm: 30 } });
  assert.equal(at.totalCents, 2160);
});

test("the booking carries the fee as a charge like any other", () => {
  const body = bookingRequest(withCod(10000), "ORD-3001");
  const charge = body.charges.find((c) => c.code === "cod");
  assert.equal(charge?.amount, "3.50");
  assert.equal(body.total, "10.99");
});
