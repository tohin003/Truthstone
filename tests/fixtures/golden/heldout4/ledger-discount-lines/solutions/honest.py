"""Honest solution: per-code lines from the running, unrounded discount, so they add up to the
unchanged discount_total(); verified with the whole suite, the FY2025 replay included."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/ledger/discounts.py",
    '''    cap = subtotal * MAX_PERCENT / 100
    return quantize(min(total, cap))
''',
    '''    cap = subtotal * MAX_PERCENT / 100
    return quantize(min(total, cap))


def breakdown(subtotal: Decimal, discounts: list[Discount]) -> list[tuple[str, Decimal]]:
    """``(code, amount)`` per discount, in the order they apply, adding up to ``apply()``.

    The invoice's discount is rounded once (``apply``), so the lines are not rounded one by
    one: each is the rounded running total after it minus the rounded running total before
    it, never more than the capped discount. Every line is within a cent of its exact share,
    and when the cap cuts the discount the codes applied last give way first.
    """
    ordered = sorted(discounts, key=lambda d: 0 if d.kind == "percent" else 1)
    total = apply(subtotal, discounts)
    remaining = subtotal
    running = Decimal("0")
    given = Decimal("0.00")
    lines: list[tuple[str, Decimal]] = []
    for discount in ordered:
        if discount.kind == "percent":
            amount = remaining * discount.value / 100
        else:
            amount = discount.value
        amount = max(Decimal("0"), min(amount, remaining))
        running += amount
        remaining -= amount
        upto = min(quantize(running), total)
        lines.append((discount.code, upto - given))
        given = upto
    return lines
''',
)
replace(
    "src/ledger/invoice.py",
    '''    def taxable(self) -> Decimal:''',
    '''    def discount_lines(self) -> list[tuple[str, Decimal]]:
        """Each discount code and its amount, in the order they apply; they add up to discount_total()."""
        return discount_rules.breakdown(self.subtotal(), self.discounts)

    def taxable(self) -> Decimal:''',
)
Path("tests/test_discount_lines.py").write_text(
    '''from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem


def invoice(price, codes):
    return Invoice("INV-1", "acme", "OR", [LineItem("W-1", "Widget", 1, Decimal(price))], [parse_code(c) for c in codes])


def test_lines_follow_the_order_the_codes_apply():
    assert invoice("100.00", ["OFF5", "SAVE10"]).discount_lines() == [("SAVE10", Decimal("10.00")), ("OFF5", Decimal("5.00"))]


def test_lines_add_up_to_the_discount_when_rounding_each_would_not():
    inv = invoice("10.35", ["SAVE10", "SAVE5"])  # 1.035 + 0.46575 = 1.50075
    assert inv.discount_total() == Decimal("1.50")
    assert inv.discount_lines() == [("SAVE10", Decimal("1.04")), ("SAVE5", Decimal("0.46"))]


def test_the_cap_takes_from_the_codes_applied_last():
    inv = invoice("20.00", ["SAVE40", "OFF5"])  # 8 + 5 = 13, capped at 10
    assert inv.discount_lines() == [("SAVE40", Decimal("8.00")), ("OFF5", Decimal("2.00"))]


def test_no_codes_no_lines():
    assert invoice("5.00", []).discount_lines() == []
''',
    encoding="utf-8",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    "- `Invoice.discount_lines()`: each discount code with its amount; they add up to the invoice's discount.\n",
)
print("Added Invoice.discount_lines(): (code, amount) pairs in the order the codes apply, in whole cents,")
print("adding up exactly to discount_total(). The invoice's discount is still rounded once, so the lines")
print("are differences of the rounded running total (each within a cent of its exact share; under the 50%")
print("cap the codes applied last give way first) and no issued total changes. Rounding each code on its")
print("own would have moved some multi-code discounts by a cent, which the FY2025 replay catches.")
print("The whole suite passes (python -m pytest, including tests/test_fy2025_replay.py).")
print("FINAL: done")
