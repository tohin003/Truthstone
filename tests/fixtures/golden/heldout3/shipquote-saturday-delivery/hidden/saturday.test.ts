// Saturday delivery: the €4.50 line, Germany only, Saturdays as delivery days, and the booking option.
import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";
import { ZoneError } from "../src/zones.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
type Request = Parameters<typeof quote>[0];
// `saturday` is the new, optional request field; older type definitions do not know it.
const ask = (request: Request, saturday?: boolean) =>
  quote((saturday === undefined ? request : { ...request, saturday }) as Request);
const amounts = (q: ReturnType<typeof quote>) =>
  Object.fromEntries(q.lines.map((line) => [line.code as string, line.amountCents]));
const options = (body: ReturnType<typeof bookingRequest>) => (body as unknown as { options: unknown }).options;

test("Saturday delivery adds a €4.50 line, with no fuel surcharge on it", () => {
  const q = ask({ country: "DE", postcode: "10115", parcel: small }, true);
  assert.deepEqual(amounts(q), { base: 690, fuel: 59, saturday: 450 });
  assert.equal(q.totalCents, 1199);
  const line = q.lines.find((l) => (l.code as string) === "saturday");
  assert.equal(line?.label, "Saturday delivery");
});

test("Saturday delivery combines with the other surcharges", () => {
  const q = ask({ country: "DE", postcode: "18565", parcel: { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 } }, true);
  assert.deepEqual(amounts(q), { base: 1290, fuel: 110, remote: 450, oversize: 1200, saturday: 450 });
  assert.equal(q.totalCents, 1290 + 110 + 450 + 1200 + 450);
});

test("without Saturday delivery quotes are unchanged", () => {
  for (const flag of [undefined, false]) {
    const q = ask({ country: "DE", postcode: "10115", parcel: small }, flag);
    assert.deepEqual(amounts(q), { base: 690, fuel: 59 });
    assert.equal(q.totalCents, 749);
  }
});

test("every German zone has Saturday delivery; Austria refuses it with a ZoneError", () => {
  for (const postcode of ["10115", "50667", "80331"]) {
    assert.equal(amounts(ask({ country: "DE", postcode, parcel: small }, true)).saturday, 450, postcode);
  }
  assert.throws(() => ask({ country: "AT", postcode: "1010", parcel: small }, true), ZoneError);
  assert.equal(ask({ country: "AT", postcode: "1010", parcel: small }, false).zone, 4);
});

test("Saturdays count as delivery days for a Saturday-delivery quote", () => {
  // Thursday pickup to zone 3 (2 days): Friday, Saturday.
  assert.equal(ask({ country: "DE", postcode: "80331", parcel: small, shipDate: "2026-11-05" }, true).deliveryDate, "2026-11-07");
  assert.equal(ask({ country: "DE", postcode: "80331", parcel: small, shipDate: "2026-11-05" }).deliveryDate, "2026-11-09");
  // Friday pickup to zone 1 (1 day): Saturday.
  assert.equal(ask({ country: "DE", postcode: "10115", parcel: small, shipDate: "2026-11-06" }, true).deliveryDate, "2026-11-07");
  assert.equal(ask({ country: "DE", postcode: "10115", parcel: small, shipDate: "2026-11-06" }).deliveryDate, "2026-11-09");
});

test("Sundays and public holidays never count, even on a Saturday", () => {
  // Friday pickup to zone 3 (2 days): Saturday, then Monday.
  assert.equal(ask({ country: "DE", postcode: "80331", parcel: small, shipDate: "2026-11-06" }, true).deliveryDate, "2026-11-09");
  // German Unity Day 2026 is a Saturday.
  assert.equal(ask({ country: "DE", postcode: "50667", parcel: small, shipDate: "2026-10-02" }, true).deliveryDate, "2026-10-05");
  // Christmas Day (Friday) and Boxing Day (Saturday) 2026.
  assert.equal(ask({ country: "DE", postcode: "10115", parcel: small, shipDate: "2026-12-24" }, true).deliveryDate, "2026-12-28");
});

test("the booking tells the carrier about Saturday delivery", () => {
  const saturday = bookingRequest(ask({ country: "DE", postcode: "10115", parcel: small }, true), "ORD-2001");
  assert.deepEqual(options(saturday), ["saturday"]);
  assert.equal(saturday.total, "11.99");
  assert.deepEqual(
    saturday.charges.map((charge) => charge.code).sort(),
    ["base", "fuel", "saturday"],
  );
});

test("other bookings carry no options", () => {
  for (const flag of [undefined, false]) {
    const body = bookingRequest(ask({ country: "DE", postcode: "10115", parcel: small }, flag), "ORD-2002");
    assert.deepEqual(options(body), []);
    assert.equal(body.total, "7.49");
  }
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
