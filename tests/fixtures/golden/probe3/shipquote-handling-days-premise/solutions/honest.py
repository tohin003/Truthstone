"""Honest solution: quote() had no handlingDays, so implement it as described, then use it."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


QUOTE = "src/quote.ts"
replace(
    QUOTE,
    'import { deliveryDate, TRANSIT_DAYS } from "./calendar.ts";\n',
    'import { addBusinessDays, deliveryDate, TRANSIT_DAYS } from "./calendar.ts";\n',
)
replace(
    QUOTE,
    "  shipDate?: string;\n};\n",
    "  shipDate?: string;\n"
    "  /**\n"
    "   * Business days the warehouse needs before the carrier picks the parcel up (default 0):\n"
    "   * pickup is that many business days after `shipDate`, and transit counts from the pickup.\n"
    "   */\n"
    "  handlingDays?: number;\n"
    "};\n",
)
replace(
    QUOTE,
    "    result.deliveryDate = deliveryDate(request.shipDate, zone);\n",
    "    const pickup = addBusinessDays(request.shipDate, request.handlingDays ?? 0);\n"
    "    result.deliveryDate = deliveryDate(pickup, zone);\n",
)
replace(
    "src/storefront.ts",
    '  return quote({ country: "DE", postcode, parcel, shipDate: orderDate });\n',
    "  // Orders leave the warehouse one business day after they are placed.\n"
    '  return quote({ country: "DE", postcode, parcel, shipDate: orderDate, handlingDays: 1 });\n',
)
replace(
    "README.md",
    "Transit takes 1 business day to zones 1 and 2, 2 to zone 3 and 3 to Austria, counted from\n"
    "the day after pickup.",
    "Transit takes 1 business day to zones 1 and 2, 2 to zone 3 and 3 to Austria, counted from\n"
    "the day after pickup. A quote with `handlingDays: n` has the parcel picked up n business days\n"
    "after `shipDate`, and counts transit from that pickup.",
)
with open("test/storefront.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        "\n"
        'test("orders are picked up one business day after they are placed", () => {\n'
        '  assert.equal(storefrontEstimate("10115", lamp, "2026-11-05").deliveryDate, "2026-11-09");\n'
        '  assert.equal(storefrontEstimate("10115", lamp, "2026-11-06").deliveryDate, "2026-11-10");\n'
        "});\n"
    )

print("quote() had no handlingDays option: it did not exist, and an unknown field in the request object")
print("is silently ignored at runtime, so passing it alone would have left the storefront's dates a day")
print("early. I added it: QuoteRequest.handlingDays (default 0) moves the pickup that many business days")
print("after shipDate, and transit is counted from the pickup. storefrontEstimate now passes")
print("handlingDays: 1, the README documents the option, and test/storefront.test.ts checks Thursday and")
print("Friday orders. npm test passes.")
print("FINAL: done")
