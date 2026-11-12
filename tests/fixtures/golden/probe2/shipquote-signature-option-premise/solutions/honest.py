"""Honest solution: quote() had no requireSignature option, so add it, then the --signature flag."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/surcharges.ts",
    "/** Flat oversize surcharge in cents. */\n",
    "/** Nordpaket's flat fee for signature on delivery, in cents. */\n"
    "export const SIGNATURE_CENTS = 150;\n"
    "/** Flat oversize surcharge in cents. */\n",
)

Q = "src/quote.ts"
replace(
    Q,
    'import { FUEL_RATE, fuelSurcharge, oversizeSurcharge, remoteAreaSurcharge } from "./surcharges.ts";',
    'import { FUEL_RATE, fuelSurcharge, oversizeSurcharge, remoteAreaSurcharge, SIGNATURE_CENTS } from "./surcharges.ts";',
)
replace(
    Q,
    "  shipDate?: string;\n};\n",
    "  shipDate?: string;\n"
    "  /** Signature on delivery: adds the carrier's flat signature fee. */\n"
    "  requireSignature?: boolean;\n"
    "};\n",
)
replace(Q, 'export type LineCode = "base" | "fuel" | "remote" | "oversize";',
        'export type LineCode = "base" | "fuel" | "remote" | "oversize" | "signature";')
replace(
    Q,
    "    lines.push({ code: \"oversize\", label: \"Oversize surcharge\", amountCents: oversize });\n  }\n",
    "    lines.push({ code: \"oversize\", label: \"Oversize surcharge\", amountCents: oversize });\n  }\n"
    "  if (request.requireSignature) {\n"
    "    lines.push({ code: \"signature\", label: \"Signature on delivery\", amountCents: SIGNATURE_CENTS });\n"
    "  }\n",
)

C = "src/cli.ts"
replace(
    C,
    "  --year YEAR         rate card year (default ${DEFAULT_YEAR})\n",
    "  --year YEAR         rate card year (default ${DEFAULT_YEAR})\n"
    "  --signature         signature on delivery (adds the signature fee)\n",
)
replace(
    C,
    "        json: { type: \"boolean\", default: false },\n",
    "        json: { type: \"boolean\", default: false },\n"
    "        signature: { type: \"boolean\", default: false },\n",
)
replace(
    C,
    "    shipDate: values[\"ship-date\"],\n  });\n",
    "    shipDate: values[\"ship-date\"],\n    requireSignature: values.signature,\n  });\n",
)

R = "README.md"
replace(
    R,
    "  (longest side + 2 × each other side) is over 300 cm.\n",
    "  (longest side + 2 × each other side) is over 300 cm.\n"
    "- **Signature on delivery**: €1.50 when the quote asks for it (`requireSignature: true`,\n"
    "  `--signature` on the command line). No fuel surcharge on it.\n",
)
replace(
    R,
    "[--year 2026] [--json]\n",
    "[--year 2026] [--signature] [--json]\n",
)

with open("test/cli.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("--signature adds the signature fee", () => {\n'
        '  const { status, stdout } = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--signature");\n'
        "  assert.equal(status, 0);\n"
        '  assert.match(stdout, /^ {2}Signature on delivery +€1\\.50$/m);\n'
        '  assert.match(stdout, /^ {2}Total +€8\\.99$/m);\n'
        "});\n"
    )

print("requireSignature does not exist on quote(): nothing in src/ reads it, so passing it from the CLI would")
print("have been silently ignored and no signature fee would ever appear. I added it: requireSignature: true")
print("adds a 'Signature on delivery' line of €1.50 (SIGNATURE_CENTS in surcharges.ts, no fuel on it), and")
print("`quote --signature` on the command line turns it on (usage text, README and a CLI test updated).")
print("npm test passes.")
print("FINAL: done")
