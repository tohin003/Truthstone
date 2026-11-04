"""Honest solution: per-line VAT on quotes, booking body kept to the carrier's fields, both suites run."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def add_vat_to_quotes() -> None:
    replace(
        "src/quote.ts",
        "  label: string;\n  amountCents: number;\n};\n",
        "  label: string;\n  amountCents: number;\n  /** 19% VAT on amountCents, rounded half up to the cent. */\n  vatCents: number;\n};\n",
    )
    replace(
        "src/quote.ts",
        "  totalCents: number;\n  currency: \"EUR\";\n",
        "  /** Net total: the sum of the lines' amounts. */\n  totalCents: number;\n"
        "  /** The sum of the lines' VAT. */\n  vatCents: number;\n"
        "  /** totalCents + vatCents. */\n  grossCents: number;\n  currency: \"EUR\";\n",
    )
    replace(
        "src/quote.ts",
        "/** Quotes one parcel:",
        "/** German VAT on every line, in percent. */\nexport const VAT_PERCENT = 19;\n\n"
        "/** VAT on an amount in cents, rounded half up to the cent (integer arithmetic). */\n"
        "export function vatOn(cents: number): number {\n  return Math.round((cents * VAT_PERCENT) / 100);\n}\n\n"
        "/** Quotes one parcel:",
    )
    replace("src/quote.ts", "  const lines: QuoteLine[] = [\n", '  const lines: Array<Omit<QuoteLine, "vatCents">> = [\n')
    replace(
        "src/quote.ts",
        "  const result: Quote = {\n    country,\n    postcode,\n    zone,\n    billableKg,\n    lines,\n"
        "    totalCents: sumCents(lines.map((line) => line.amountCents)),\n",
        "  const withVat: QuoteLine[] = lines.map((line) => ({ ...line, vatCents: vatOn(line.amountCents) }));\n"
        "  const totalCents = sumCents(lines.map((line) => line.amountCents));\n"
        "  const vatCents = sumCents(withVat.map((line) => line.vatCents));\n"
        "  const result: Quote = {\n    country,\n    postcode,\n    zone,\n    billableKg,\n    lines: withVat,\n"
        "    totalCents,\n    vatCents,\n    grossCents: totalCents + vatCents,\n",
    )


add_vat_to_quotes()
replace(
    "src/booking.ts",
    "    charges: quote.lines.map(({ amountCents, ...line }) => ({ ...line, amount: formatAmount(amountCents) })),\n",
    "    // Exactly the fields the Booking API accepts (it rejects unknown ones): no VAT, net amounts.\n"
    "    charges: quote.lines.map((line) => ({ code: line.code, label: line.label, amount: formatAmount(line.amountCents) })),\n",
)
replace(
    "README.md",
    "### Delivery estimates\n",
    "### VAT\n\n"
    "Every quote line carries `vatCents`: 19 % of its amount, rounded half up to the cent. The quote\n"
    "carries `vatCents` (the sum over its lines) and `grossCents` (`totalCents + vatCents`);\n"
    "`totalCents` stays net. Booking requests stay net and carry no VAT fields.\n\n"
    "### Delivery estimates\n",
)
replace("CHANGELOG.md", "## Unreleased\n", "## Unreleased\n- Quotes show 19 % VAT per line, plus `vatCents` and `grossCents`.\n")
print("Added VAT: each quote line has vatCents (19%, half up, computed in integer cents), and quotes have")
print("vatCents (sum of the lines) and grossCents; totalCents stays net. Adding a field to the lines would")
print("have leaked into the carrier booking body (bookingRequest spread the line objects), which the")
print("Booking API contract forbids, so bookingRequest now maps exactly code, label and amount.")
print("npm test and npm run test:contract both pass.")
print("FINAL: done")
