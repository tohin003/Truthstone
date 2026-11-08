import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({ weightKg, lengthCm, widthCm, heightCm });
const oversizeLine = (q: ReturnType<typeof quote>) => q.lines.find((line) => line.code === "oversize");
const LONGEST = "Oversize surcharge (longest side over 120 cm)";
const GIRTH = "Oversize surcharge (length plus girth over 300 cm)";

test("a parcel with a side over 120 cm says so", () => {
  const q = quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) });
  assert.deepEqual(oversizeLine(q), { code: "oversize", label: LONGEST, amountCents: 1200 });
});

test("a flat parcel over 300 cm in length plus girth says that instead", () => {
  // 120 x 89 x 2 cm: no side over 120, but 120 + 2 x 89 + 2 x 2 = 302.
  const q = quote({ country: "DE", postcode: "10115", parcel: box(3, 89, 120, 2) });
  assert.deepEqual(oversizeLine(q), { code: "oversize", label: GIRTH, amountCents: 1200 });
});

test("when both are true the longest side is named", () => {
  // 200 x 30 x 21 cm: longest side 200, length plus girth 302.
  const q = quote({ country: "AT", postcode: "1010", parcel: box(8, 21, 30, 200) });
  assert.equal(oversizeLine(q)?.label, LONGEST);
  assert.equal(oversizeLine(q)?.amountCents, 1200);
});

test("exactly at the limits there is no oversize line, as before", () => {
  assert.equal(oversizeLine(quote({ country: "DE", postcode: "10115", parcel: box(1, 120, 10, 10) })), undefined);
  // 120 x 88 x 2 cm: length plus girth exactly 300.
  assert.equal(oversizeLine(quote({ country: "DE", postcode: "10115", parcel: box(1, 120, 88, 2) })), undefined);
});

test("the other lines and the total are unchanged", () => {
  const q = quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) });
  assert.deepEqual(q.lines.map((line) => [line.code, line.amountCents]), [["base", 1490], ["fuel", 127], ["oversize", 1200]]);
  assert.equal(q.lines[0].label, "Base rate, zone 3 (Germany South), up to 20 kg");
  assert.equal(q.totalCents, 2817);
});

test("the command line and the booking request carry the new label", () => {
  let stdout = "";
  const status = main(["quote", "--postcode", "10115", "--weight", "3", "--dims", "120x89x2"], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
  });
  assert.equal(status, 0);
  assert.match(stdout, /^ {2}Oversize surcharge \(length plus girth over 300 cm\) +€12\.00$/m);
  const body = bookingRequest(quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) }), "ORD-2001");
  assert.deepEqual(body.charges[2], { code: "oversize", label: LONGEST, amount: "12.00" });
});
