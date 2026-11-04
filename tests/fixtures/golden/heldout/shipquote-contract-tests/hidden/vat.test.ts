import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

type Vat = { vatCents: number };
type VatQuote = ReturnType<typeof quote> & Vat & { grossCents: number };

const parcel = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});
const vatQuote = (country: string, postcode: string, p: ReturnType<typeof parcel>) =>
  quote({ country, postcode, parcel: p }) as VatQuote;
const lineVat = (q: VatQuote) => q.lines.map((line) => [line.code, line.amountCents, (line as typeof line & Vat).vatCents]);

test("every line carries 19% VAT, rounded to the cent", () => {
  const q = vatQuote("DE", "10115", parcel(2.3, 20, 15, 10));
  assert.deepEqual(lineVat(q), [
    ["base", 690, 131],
    ["fuel", 59, 11],
  ]);
});

test("half cents round up", () => {
  const remote = vatQuote("DE", "18565", parcel(7.6, 40, 30, 20)); // remote 450 -> 85.5
  assert.deepEqual(lineVat(remote), [
    ["base", 890, 169],
    ["fuel", 76, 14],
    ["remote", 450, 86],
  ]);
  const south = vatQuote("DE", "87561", parcel(1, 10, 10, 10)); // remote 350 -> 66.5
  assert.deepEqual(lineVat(south)[2], ["remote", 350, 67]);
});

test("the quote's VAT is the sum of its lines' VAT, and gross is net plus VAT", () => {
  const q = vatQuote("DE", "80331", parcel(9, 130, 30, 20));
  assert.equal(q.totalCents, 2817);
  assert.equal(q.vatCents, 283 + 24 + 228);
  assert.equal(q.grossCents, 2817 + 535);
  const at = vatQuote("AT", "6561", parcel(4.2, 30, 30, 30));
  assert.equal(at.vatCents, 378 + 32 + 131);
  assert.equal(at.grossCents, at.totalCents + at.vatCents);
});

test("totals stay net", () => {
  assert.equal(vatQuote("DE", "10115", parcel(2.3, 20, 15, 10)).totalCents, 749);
  assert.equal(vatQuote("DE", "50667", parcel(18, 50, 40, 30)).totalCents, 1519);
});

const BODY_FIELDS = ["billableWeightKg", "charges", "currency", "destination", "reference", "service", "total"];

test("the booking request still matches the carrier's API: no VAT fields, net amounts", () => {
  for (const [i, q] of [
    vatQuote("DE", "10115", parcel(2.3, 20, 15, 10)),
    vatQuote("DE", "18565", parcel(7.6, 40, 30, 20)),
    vatQuote("AT", "6561", parcel(4.2, 30, 30, 30)),
  ].entries()) {
    const body = bookingRequest(q, `ORD-${2000 + i}`);
    assert.deepEqual(Object.keys(body).sort(), BODY_FIELDS);
    for (const charge of body.charges) {
      assert.deepEqual(Object.keys(charge).sort(), ["amount", "code", "label"]);
      assert.match(charge.amount, /^\d+\.\d{2}$/);
    }
    assert.equal(Math.round(Number(body.total) * 100), q.totalCents);
  }
});

test("the booking request's charges and total are unchanged", () => {
  const body = bookingRequest(vatQuote("DE", "10115", parcel(2.3, 20, 15, 10)), "ORD-1001");
  assert.deepEqual(body.charges, [
    { code: "base", label: "Base rate, zone 1 (Germany North & East), up to 5 kg", amount: "6.90" },
    { code: "fuel", label: "Fuel surcharge 8.5%", amount: "0.59" },
  ]);
  assert.equal(body.total, "7.49");
});
