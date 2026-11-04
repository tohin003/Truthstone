"""The documented rule: an invoice total is never negative; credits beyond the charges clamp to zero."""

from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem


def make(*lines, region="CA", discounts=()):
    return Invoice(
        "INV-1",
        "acme",
        region,
        [LineItem(sku, sku.lower(), quantity, Decimal(price)) for sku, quantity, price in lines],
        [parse_code(code) for code in discounts],
    )


def test_a_credit_only_invoice_totals_zero():
    invoice = make(("RET-1", -2, "15.00"))
    assert invoice.subtotal() == Decimal("-30.00")
    assert invoice.tax() == Decimal("0.00")
    assert invoice.total() == Decimal("0.00")


def test_credits_beyond_the_charges_clamp_to_zero():
    invoice = make(("W-1", 2, "10.00"), ("RET-1", -3, "10.00"))
    assert invoice.tax() == Decimal("0.00")
    assert invoice.total() == Decimal("0.00")


def test_charges_beyond_the_credits_are_taxed_on_the_difference():
    invoice = make(("W-1", 5, "10.00"), ("RET-1", -2, "10.00"))
    assert invoice.subtotal() == Decimal("30.00")
    assert invoice.total() == Decimal("32.18")


def test_no_total_is_ever_negative():
    for charges in range(4):
        for credits in range(4):
            for region in ("CA", "NY", "OR"):
                lines = []
                if charges:
                    lines.append(("W-1", charges, "7.50"))
                if credits:
                    lines.append(("RET-1", -credits, "9.99"))
                assert make(*lines, region=region).total() >= 0, (charges, credits, region)


def test_ordinary_invoices_are_unchanged():
    lines = (("W-1", 3, "9.99"), ("G-2", 1, "25.00"))
    assert make(*lines).total() == Decimal("58.96")
    assert make(*lines, discounts=["SAVE10"]).total() == Decimal("53.06")
    assert make(*lines, region="OR").total() == Decimal("54.97")
