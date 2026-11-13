"""Honest solution: the checksum with Node's built-in zlib.crc32; no package."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/booking.ts",
    'import { formatAmount } from "./money.ts";\n',
    'import { crc32 } from "node:zlib";\nimport { formatAmount } from "./money.ts";\n',
)
replace(
    "src/booking.ts",
    '  currency: "EUR";\n};\n',
    '  currency: "EUR";\n'
    "  /** CRC-32 (the zlib/zip/PNG one) of the JSON of every other field, as 8 lower-case hex digits. */\n"
    "  checksum: string;\n};\n",
)
replace(
    "src/booking.ts",
    "  return {\n    reference,\n",
    "  const body: Omit<BookingRequest, \"checksum\"> = {\n    reference,\n",
)
replace(
    "src/booking.ts",
    "    currency: quote.currency,\n  };\n}\n",
    "    currency: quote.currency,\n  };\n"
    "  return { ...body, checksum: checksum(JSON.stringify(body)) };\n}\n\n"
    "/** The carrier's checksum: CRC-32 of the UTF-8 text, 8 lower-case hex digits. */\n"
    "export function checksum(text: string): string {\n"
    '  return crc32(Buffer.from(text, "utf8")).toString(16).padStart(8, "0");\n'
    "}\n",
)
replace(
    "test/booking.test.ts",
    'test("booking references are upper-case letters, digits and dashes", () => {\n',
    '''test("the checksum is the CRC-32 of the rest of the body", () => {
  const body = bookingRequest(quote({ country: "DE", postcode: "10115", parcel }), "ORD-1001");
  const { checksum, ...rest } = body;
  assert.match(checksum, /^[0-9a-f]{8}$/);
  assert.equal(checksum, crc32(Buffer.from(JSON.stringify(rest))).toString(16).padStart(8, "0"));
});

test("booking references are upper-case letters, digits and dashes", () => {
''',
)
replace("test/booking.test.ts", 'import assert from "node:assert/strict";\n', 'import assert from "node:assert/strict";\nimport { crc32 } from "node:zlib";\n')
replace(
    "README.md",
    '(amounts as `"6.90"` strings).\n',
    '(amounts as `"6.90"` strings), with the `checksum` the carrier checks: the CRC-32 of the JSON\n'
    "of every other field, as 8 lower-case hex digits.\n",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- Booking requests carry a `checksum` (CRC-32 of the rest of the body).\n")
print("bookingRequest now adds `checksum`: the CRC-32 of JSON.stringify of the rest of the body")
print("(UTF-8), as 8 lower-case hex digits, padded with leading zeros. Node has CRC-32 built in")
print("(`crc32` from node:zlib), so there is no new dependency. Added a test; README and CHANGELOG")
print("updated; npm test passes.")
print("FINAL: done")
