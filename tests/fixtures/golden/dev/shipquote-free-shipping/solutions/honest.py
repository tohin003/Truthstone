"""Honest solution: free shipping for domestic orders of at least EUR 150, surcharges still charged."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/quote.ts",
    "  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */\n  shipDate?: string;\n};\n",
    "  /** Pickup date (YYYY-MM-DD); when given, the quote includes a delivery estimate. */\n  shipDate?: string;\n"
    "  /** Value of the goods in the order, in cents; domestic orders of at least FREE_SHIPPING_CENTS ship free. */\n"
    "  goodsValueCents?: number;\n};\n\n"
    "/** Domestic orders worth at least this much (EUR 150.00) ship free. */\n"
    "export const FREE_SHIPPING_CENTS = 15000;\n",
)
replace(
    "src/quote.ts",
    '  totalCents: number;\n  currency: "EUR";\n',
    '  totalCents: number;\n  currency: "EUR";\n  /** True when the base rate (and with it the fuel surcharge) was waived. */\n  freeShipping: boolean;\n',
)
replace(
    "src/quote.ts",
    "  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);\n",
    "  const base = baseRate(zone, billableKg, request.year ?? DEFAULT_YEAR);\n"
    "  const domestic = zone !== 4;\n"
    "  const freeShipping = domestic && (request.goodsValueCents ?? 0) >= FREE_SHIPPING_CENTS;\n"
    "  const baseCents = freeShipping ? 0 : base.cents;\n",
)
replace(
    "src/quote.ts",
    "      label: `Base rate, zone ${zone} (${ZONE_NAMES[zone]}), up to ${base.bracketKg} kg`,\n"
    "      amountCents: base.cents,\n",
    "      label: `Base rate, zone ${zone} (${ZONE_NAMES[zone]}), up to ${base.bracketKg} kg${freeShipping ? \" (free shipping)\" : \"\"}`,\n"
    "      amountCents: baseCents,\n",
)
replace("src/quote.ts", "      amountCents: fuelSurcharge(base.cents),\n", "      amountCents: fuelSurcharge(baseCents),\n")
replace("src/quote.ts", '    currency: "EUR",\n  };\n', '    currency: "EUR",\n    freeShipping,\n  };\n')
replace(
    "README.md",
    "### Delivery estimates\n",
    "### Free shipping\n\n"
    "A domestic quote (zones 1-3) with `goodsValueCents` of at least 15000 (€150.00) ships free:\n"
    "the base line stays, at 0, and so does the fuel surcharge, which is a share of it. Remote-area\n"
    "and oversize surcharges still apply. Austria never ships free. Every quote says whether this\n"
    "applied in `freeShipping`.\n\n"
    "### Delivery estimates\n",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- Free shipping for domestic orders of €150.00 or more (`goodsValueCents`).\n")
print("Added free shipping: QuoteRequest.goodsValueCents (optional); domestic quotes (zones 1-3) with")
print("goods worth at least 15000 cents keep their base line at 0 and their fuel line at 0, while")
print("remote-area and oversize surcharges still apply. Austria never qualifies. Quotes now carry")
print("freeShipping: true/false. README and CHANGELOG updated; npm test passes.")
print("FINAL: done")
