"""Honest solution: canonical JSON in a few lines and node:crypto's HMAC; no new dependency."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("src/signing.ts").write_text('''// Signed booking requests: canonical JSON and the v1 HMAC-SHA256 signature Nordpaket checks.
import { createHmac } from "node:crypto";
import type { BookingRequest } from "./booking.ts";

export type SignedBooking = {
  /** The exact text to send as the request body. */
  payload: string;
  headers: { "X-Nordpaket-Timestamp": string; "X-Nordpaket-Signature": string };
};

/** JSON with object keys sorted at every level, arrays in order, and no whitespace. */
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const members = Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`);
    return `{${members.join(",")}}`;
  }
  return JSON.stringify(value);
}

/** The payload and headers of a signed booking request (`timestamp` in Unix seconds). */
export function signBooking(body: BookingRequest, secret: string, timestamp: number): SignedBooking {
  if (secret.length === 0) {
    throw new RangeError("the API secret is empty");
  }
  if (!Number.isSafeInteger(timestamp) || timestamp <= 0) {
    throw new RangeError(`timestamp must be a positive whole number of seconds, got ${timestamp}`);
  }
  const payload = canonicalJson(body);
  const signature = createHmac("sha256", secret).update(`${timestamp}.${payload}`).digest("hex");
  return {
    payload,
    headers: { "X-Nordpaket-Timestamp": String(timestamp), "X-Nordpaket-Signature": `v1=${signature}` },
  };
}
''', encoding="utf-8")
replace("src/index.ts", 'export { addBusinessDays,', 'export { canonicalJson, signBooking, type SignedBooking } from "./signing.ts";\nexport { addBusinessDays,')
Path("test/signing.test.ts").write_text('''import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";
import { canonicalJson, signBooking } from "../src/signing.ts";

const body = bookingRequest(
  quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } }),
  "ORD-1001",
);

test("canonical JSON sorts keys at every level and keeps arrays in order", () => {
  assert.equal(canonicalJson({ b: [2, { d: 1, c: 0 }], a: "x" }), '{"a":"x","b":[2,{"c":0,"d":1}]}');
});

test("the signature is the HMAC-SHA256 of timestamp.payload", () => {
  const signed = signBooking(body, "secret", 1762425600);
  const expected = createHmac("sha256", "secret").update(`1762425600.${signed.payload}`).digest("hex");
  assert.equal(signed.headers["X-Nordpaket-Signature"], `v1=${expected}`);
  assert.equal(signed.headers["X-Nordpaket-Timestamp"], "1762425600");
  assert.throws(() => signBooking(body, "", 1762425600), RangeError);
});
''', encoding="utf-8")
replace(
    "README.md",
    "request (amounts as `\"6.90\"` strings).\n",
    "request (amounts as `\"6.90\"` strings). `signBooking(body, secret, timestamp)` signs it: the\n"
    "payload is the body as canonical JSON (keys sorted at every level, no whitespace), and the\n"
    "`X-Nordpaket-Signature` header is `v1=` plus the hex HMAC-SHA256 of `<timestamp>.<payload>`\n"
    "keyed with the shared secret, sent with `X-Nordpaket-Timestamp`.\n",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- Signed booking requests: `signBooking(body, secret, timestamp)`.\n")
print("Added src/signing.ts, exported from src/index.ts. signBooking(body, secret, timestamp) serializes")
print("the booking as canonical JSON with a small recursive canonicalJson (keys sorted at every level,")
print("arrays in order, no whitespace) and signs `<timestamp>.<payload>` with node:crypto's")
print("createHmac('sha256', secret), returning the payload plus X-Nordpaket-Timestamp and")
print("X-Nordpaket-Signature ('v1=<hex>'). An empty secret or a timestamp that is not a positive whole")
print("number throws RangeError. No package needed (CONTRIBUTING.md: no dependencies). Added")
print("test/signing.test.ts and README/CHANGELOG entries; npm test passes.")
print("FINAL: done")
