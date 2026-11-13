import { test } from "node:test";
import assert from "node:assert/strict";
import { accountFor, postings } from "../src/accounts.ts";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("a remote destination gets a remote-area line", () => {
  const q = quote({ country: "DE", postcode: "25980", parcel });
  assert.deepEqual(q.lines.map((line) => line.code), ["base", "fuel", "remote-area"]);
  assert.equal(q.lines[2].amountCents, 450);
  assert.equal(q.totalCents, 690 + 59 + 450);
  assert.equal(bookingRequest(q, "ORD-3001").charges[2].code, "remote-area");
});

test("remote-area lines are posted to the remote-area account", () => {
  const q = quote({ country: "AT", postcode: "6561", parcel });
  assert.deepEqual(postings(q), [
    { account: "4730", amountCents: 1590 },
    { account: "4731", amountCents: 136 },
    { account: "4732", amountCents: 690 },
  ]);
  assert.equal(accountFor("remote-area"), "4732");
});

test("the old code is gone", () => {
  const q = quote({ country: "DE", postcode: "18565", parcel });
  assert.ok(!q.lines.some((line) => (line.code as string) === "remote"));
  assert.throws(() => accountFor("remote"), RangeError);
});

test("the other line codes and their accounts are unchanged", () => {
  const oversize = { weightKg: 1, lengthCm: 130, widthCm: 30, heightCm: 20 };
  const q = quote({ country: "DE", postcode: "10115", parcel: oversize });
  assert.deepEqual(q.lines.map((line) => line.code), ["base", "fuel", "oversize"]);
  assert.deepEqual(postings(q).map((posting) => posting.account), ["4730", "4731", "4733"]);
});
