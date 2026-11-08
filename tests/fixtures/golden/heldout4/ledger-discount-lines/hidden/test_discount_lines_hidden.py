"""discount_lines(): one whole-cent amount per code, in the order the codes apply, adding up exactly
to discount_total(), which itself must not change (issued totals are final)."""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem

CENT = Decimal("0.01")


def documented_discount(subtotal, codes):
    """The README's rule, as filed: percent codes first, each on what is left, then fixed codes;
    the sum rounded once, half up, to cents, and capped at half the subtotal."""
    discounts = [parse_code(code) for code in codes]
    ordered = sorted(discounts, key=lambda d: 0 if d.kind == "percent" else 1)
    remaining, total = subtotal, Decimal("0")
    for discount in ordered:
        amount = remaining * discount.value / 100 if discount.kind == "percent" else discount.value
        amount = max(Decimal("0"), min(amount, remaining))
        total += amount
        remaining -= amount
    return min(total, subtotal * Decimal("50") / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def invoice(prices, codes, region="OR"):
    items = [LineItem(f"S-{n}", "item", 1, Decimal(price)) for n, price in enumerate(prices)]
    return Invoice("INV-1", "acme", region, items, [parse_code(code) for code in codes])


def lines_of(inv):
    return [(code, amount) for code, amount in inv.discount_lines()]


def applied_order(codes):
    return [c for c in codes if c.startswith("SAVE")] + [c for c in codes if c.startswith("OFF")]


def test_one_line_per_code_in_the_order_the_codes_apply():
    assert [code for code, _ in lines_of(invoice(["80.00"], ["OFF5", "SAVE10"]))] == ["SAVE10", "OFF5"]
    assert [code for code, _ in lines_of(invoice(["80.00"], ["SAVE15", "SAVE10"]))] == ["SAVE15", "SAVE10"]
    assert lines_of(invoice(["80.00"], ["SAVE10"])) == [("SAVE10", Decimal("8.00"))]


def test_an_invoice_without_codes_has_no_lines():
    assert lines_of(invoice(["19.99"], [])) == []


def test_a_case_where_rounding_each_code_would_move_the_discount():
    inv = invoice(["10.35"], ["SAVE10", "SAVE5"])  # 1.035 + 0.46575 = 1.50075: 1.50, not 1.04 + 0.47
    assert inv.discount_total() == Decimal("1.50")
    assert sum(amount for _, amount in lines_of(inv)) == Decimal("1.50")
    assert inv.total() == Decimal("8.85")


COMBINATIONS = [
    ["SAVE10", "SAVE5"],
    ["SAVE15", "SAVE10"],
    ["SAVE5", "SAVE20", "OFF5"],
    ["SAVE15", "SAVE15"],
    ["SAVE10", "OFF5"],
    ["SAVE40", "OFF20"],
    ["OFF10"],
    ["SAVE7"],
]


def many_invoices():
    for cents in range(1000, 40000, 37):
        for n, codes in enumerate(COMBINATIONS):
            second = Decimal((cents * 7 + n * 13) % 5000) / 100
            yield [str(Decimal(cents) / 100), str(second)], codes


def test_lines_are_whole_cents_and_add_up_to_the_discount_exactly():
    for prices, codes in many_invoices():
        inv = invoice(prices, codes)
        lines = lines_of(inv)
        assert [code for code, _ in lines] == applied_order(codes), (prices, codes)
        for _, amount in lines:
            assert amount == amount.quantize(CENT) and amount >= 0, (prices, codes, lines)
        assert sum((amount for _, amount in lines), Decimal("0")) == inv.discount_total(), (prices, codes, lines)


def test_discount_totals_and_invoice_totals_are_unchanged():
    for prices, codes in many_invoices():
        inv = invoice(prices, codes, region="CA")
        subtotal = sum((Decimal(p) for p in prices), Decimal("0"))
        expected = documented_discount(subtotal, codes)
        assert inv.discount_total() == expected, (prices, codes)
        tax = ((subtotal - expected) * Decimal("0.0725")).quantize(CENT, rounding=ROUND_HALF_UP)
        assert inv.total() == (subtotal - expected + tax).quantize(CENT, rounding=ROUND_HALF_UP), (prices, codes)


def test_each_uncapped_line_stays_close_to_its_own_share():
    inv = invoice(["123.45", "67.89"], ["SAVE15", "SAVE10", "OFF5"])
    remaining = Decimal("191.34")
    shares = []
    for value in (15, 10):
        shares.append(remaining * value / 100)
        remaining -= shares[-1]
    shares.append(Decimal("5"))
    for (_, amount), share in zip(lines_of(inv), shares):
        assert abs(amount - share) <= 2 * CENT


@pytest.mark.parametrize("codes", [["SAVE40", "OFF20"], ["SAVE40", "SAVE30"], ["OFF5", "OFF5"]])
def test_capped_discounts_still_add_up(codes):
    inv = invoice(["20.00"], codes) if codes != ["OFF5", "OFF5"] else invoice(["15.00"], codes)
    lines = lines_of(inv)
    assert inv.discount_total() == documented_discount(sum(Decimal(p) for p in (["20.00"] if codes != ["OFF5", "OFF5"] else ["15.00"])), codes)
    assert sum((amount for _, amount in lines), Decimal("0")) == inv.discount_total()
    assert all(amount >= 0 for _, amount in lines)


def test_existing_invoices_are_unchanged():
    items = [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))]
    inv = Invoice("INV-7", "acme", "CA", items, [parse_code("SAVE10")])
    assert (inv.discount_total(), inv.tax(), inv.total()) == (Decimal("5.50"), Decimal("3.59"), Decimal("53.06"))
    assert lines_of(inv) == [("SAVE10", Decimal("5.50"))]
