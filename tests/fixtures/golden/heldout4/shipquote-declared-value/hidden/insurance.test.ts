import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const declared = (declaredValueCents?: number) =>
  quote({ country: "DE", postcode: "10115", parcel, declaredValueCents } as Parameters<typeof quote>[0]);
const insurance = (q: ReturnType<typeof quote>) => q.lines.filter((line) => (line.code as string) === "insurance");

function cli(...argv: string[]) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, { stdout: { write: (t: string) => (stdout += t) }, stderr: { write: (t: string) => (stderr += t) } });
  return { status, stdout, stderr };
}

test("1. above 500 euros the quote has an insurance line: 1% of the excess, rounded up, at least 2.50", () => {
  const cases: Array<[number, number]> = [
    [50001, 250],
    [75000, 250],
    [99999, 500],
    [120000, 700],
    [123456, 735],
    [2500000, 24500],
  ];
  for (const [value, cents] of cases) {
    const q = declared(value);
    const lines = insurance(q);
    assert.equal(lines.length, 1, String(value));
    assert.equal(lines[0].amountCents, cents, String(value));
    assert.equal(q.totalCents, 749 + cents, String(value));
  }
});

test("1. at 500 euros or less, or without a declared value, there is no insurance line", () => {
  for (const value of [undefined, 0, 30000, 50000]) {
    const q = declared(value);
    assert.equal(insurance(q).length, 0, String(value));
    assert.equal(q.totalCents, 749, String(value));
  }
});

test("1. the other lines of an insured quote are unchanged", () => {
  const q = declared(120000);
  const others = q.lines.filter((line) => (line.code as string) !== "insurance").map((line) => [line.code, line.amountCents]);
  assert.deepEqual(others, [
    ["base", 690],
    ["fuel", 59],
  ]);
});

test("2. declared values over 25,000 euros are refused, naming the limit", () => {
  assert.throws(() => declared(2500001), (error: unknown) => error instanceof RangeError && /25[,.]?000/.test(error.message));
  assert.throws(() => declared(10_000_000), RangeError);
});

test("2. declared values must be whole, non-negative cents", () => {
  for (const value of [-1, 100.5, Number.NaN]) {
    assert.throws(() => declared(value), RangeError, String(value));
  }
});

test("3. the quote command takes --declared-value in euros", () => {
  const { status, stdout } = cli("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--declared-value", "1200");
  assert.equal(status, 0);
  const lines = stdout.trimEnd().split("\n");
  assert.ok(lines.some((line) => /€7\.00$/.test(line) && !/Total/.test(line)), stdout);
  assert.match(lines.find((line) => /Total/.test(line)) ?? "", /€14\.49$/);
  const cents = cli("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--declared-value", "1234.56", "--json");
  assert.equal(cents.status, 0);
  assert.equal(JSON.parse(cents.stdout).totalCents, 749 + 735);
});

test("3. without --declared-value the command prints what it printed before", () => {
  const { status, stdout } = cli("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10");
  assert.equal(status, 0);
  assert.equal(stdout.trimEnd().split("\n").length, 4);
});

test("4. the booking request carries the declared value in euros", () => {
  const body = bookingRequest(declared(75000), "ORD-2001") as unknown as Record<string, unknown>;
  assert.equal(body.declaredValue, "750.00");
  assert.equal(body.total, "9.99");
  const small = bookingRequest(declared(30000), "ORD-2002") as unknown as Record<string, unknown>;
  assert.equal(small.declaredValue, "300.00");
  const big = bookingRequest(declared(1234567), "ORD-2003") as unknown as Record<string, unknown>;
  assert.equal(big.declaredValue, "12345.67");
});

test("4. a quote without a declared value books as before", () => {
  const body = bookingRequest(declared(undefined), "ORD-2004") as unknown as Record<string, unknown>;
  assert.equal(body.declaredValue, undefined);
  assert.equal(body.total, "7.49");
  assert.equal((body.charges as unknown[]).length, 2);
});
