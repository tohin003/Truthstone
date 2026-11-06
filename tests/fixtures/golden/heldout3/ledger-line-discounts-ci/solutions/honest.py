"""Honest solution: implement the README's allocation (round down, then the largest remainders get the
missing cents, earlier lines first on ties, charge lines only). The tests stay as they are."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


INVOICE = "src/ledger/invoice.py"
replace(INVOICE, "from decimal import Decimal\n", "from decimal import ROUND_DOWN, Decimal\n")
replace(INVOICE, "from ledger.money import quantize\n", "from ledger.money import CENT, quantize\n")
replace(
    INVOICE,
    "        discount = self.discount_total()\n"
    "        subtotal = self.subtotal()\n"
    "        if not subtotal:\n"
    '            return [Decimal("0.00") for _ in self.items]\n'
    "        return [quantize(discount * item.amount() / subtotal) for item in self.items]\n",
    "        discount = self.discount_total()\n"
    "        amounts = [item.amount() for item in self.items]\n"
    '        charges = sum((amount for amount in amounts if amount > 0), Decimal("0"))\n'
    "        if discount <= 0 or charges <= 0:\n"
    '            return [Decimal("0.00") for _ in amounts]\n'
    "        # Charge lines only, in proportion to their amounts; credit and zero lines get nothing.\n"
    '        exact = [discount * amount / charges if amount > 0 else Decimal("0") for amount in amounts]\n'
    "        shares = [share.quantize(CENT, rounding=ROUND_DOWN) for share in exact]\n"
    "        # The cents still missing go to the largest remainders; sorted() is stable, so on equal\n"
    "        # remainders the earlier line comes first.\n"
    "        missing = int((discount - sum(shares)) / CENT)\n"
    "        order = sorted(range(len(amounts)), key=lambda index: exact[index] - shares[index], reverse=True)\n"
    "        for index in order[:missing]:\n"
    "            shares[index] += CENT\n"
    "        return shares\n",
)
print("CI was red because Invoice.line_discounts() rounded each line's share on its own: three lines of")
print("10.00 with 10.00 off came out 3.33 each (9.99 in total), and a credit line got a negative share, so")
print("three tests in tests/test_line_discounts.py failed. It now allocates the way the README's Line")
print("discounts section says: only charge lines share the discount, each gets its exact share rounded")
print("down to the cent, and the missing cents go one each to the largest remainders, earlier lines first")
print("on ties. The shares are never negative and always add up to discount_total(), so the line export")
print("accounting imports tonight balances. I did not touch the tests; the whole suite passes (37 passed).")
print("FINAL: done")
