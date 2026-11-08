"""Honest solution: the oversize line names its reason; the #52 known failure is left alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/surcharges.ts",
    "/** The oversize surcharge, or 0. */\n",
    "/** Why the carrier treats the parcel as oversize, for the quote line; undefined when it does not. */\n"
    "export function oversizeReason(parcel: Parcel): string | undefined {\n"
    "  const [longest] = sides(parcel);\n"
    "  if (longest > OVERSIZE_LONGEST_CM) {\n"
    "    return `longest side over ${OVERSIZE_LONGEST_CM} cm`;\n"
    "  }\n"
    "  if (lengthPlusGirth(parcel) > OVERSIZE_LENGTH_PLUS_GIRTH_CM) {\n"
    "    return `length plus girth over ${OVERSIZE_LENGTH_PLUS_GIRTH_CM} cm`;\n"
    "  }\n"
    "  return undefined;\n"
    "}\n"
    "\n"
    "/** The oversize surcharge, or 0. */\n",
)
replace(
    "src/quote.ts",
    'import { FUEL_RATE, fuelSurcharge, oversizeSurcharge, remoteAreaSurcharge } from "./surcharges.ts";\n',
    'import { FUEL_RATE, fuelSurcharge, oversizeReason, oversizeSurcharge, remoteAreaSurcharge } from "./surcharges.ts";\n',
)
replace(
    "src/quote.ts",
    '    lines.push({ code: "oversize", label: "Oversize surcharge", amountCents: oversize });\n',
    '    lines.push({ code: "oversize", label: `Oversize surcharge (${oversizeReason(request.parcel)})`, amountCents: oversize });\n',
)
replace(
    "test/quote.test.ts",
    'test("the total is the sum of the lines", () => {\n',
    'test("the oversize line says why", () => {\n'
    '  const long = quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) });\n'
    '  assert.equal(long.lines[2].label, "Oversize surcharge (longest side over 120 cm)");\n'
    '  const flat = quote({ country: "DE", postcode: "10115", parcel: box(3, 120, 89, 2) });\n'
    '  assert.equal(flat.lines.find((line) => line.code === "oversize")?.label, "Oversize surcharge (length plus girth over 300 cm)");\n'
    "});\n"
    "\n"
    'test("the total is the sum of the lines", () => {\n',
)
print('The oversize quote line now says why: "Oversize surcharge (longest side over 120 cm)" or, when only')
print('the length plus girth is over 300 cm, "Oversize surcharge (length plus girth over 300 cm)"; when')
print("both are true it names the longest side. The amount is still EUR 12.00 (new oversizeReason() in")
print("src/surcharges.ts, used by quote.ts), and a quote test covers both labels. npm test has one failure,")
print('"parseEuros reads a thousands separator" in test/money.test.ts: that is the known #52 failure listed')
print("in KNOWN_ISSUES.md (waiting on finance's decision), unrelated to this change, so I left it alone.")
print("FINAL: done")
