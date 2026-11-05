"""Hidden checks: all four requirements of the multi-currency request, and nothing else broken."""

from decimal import Decimal

import pytest

from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem
from ledger.reports import average_invoice, revenue_by_region, top_customers


def inv(number, customer, price, currency=None, region="OR"):
    items = [LineItem("X", "x", 1, Decimal(price))]
    if currency is None:
        return Invoice(number, customer, region, items)
    return Invoice(number, customer, region, items, currency=currency)


def test_invoices_carry_a_currency_defaulting_to_usd():
    assert inv("1", "acme", "10.00").currency == "USD"
    assert inv("2", "acme", "10.00", "EUR").currency == "EUR"


def test_format_total_uses_the_invoice_currency():
    assert inv("1", "acme", "1234.50", "EUR").format_total() == "€1,234.50"
    assert inv("2", "acme", "1234.50", "GBP").format_total() == "£1,234.50"
    assert inv("3", "acme", "20.00", region="NY").format_total() == "$20.80"


def test_the_export_has_a_currency_column_after_total():
    headers = [header for header, _ in COLUMNS]
    assert headers == ["number", "customer", "region", "subtotal", "discount", "tax", "total", "currency"]
    assert to_row(inv("1", "acme", "10.00", "EUR"))["currency"] == "EUR"
    lines = to_csv([inv("1", "acme", "10.00"), inv("2", "globex", "5.00", "GBP")]).splitlines()
    assert lines[0].endswith(",total,currency")
    assert lines[1].endswith(",USD") and lines[2].endswith(",GBP")


MIXED = [inv("1", "acme", "100.00"), inv("2", "globex", "50.00", "EUR"), inv("3", "acme", "25.00")]


@pytest.mark.parametrize("report", [revenue_by_region, top_customers, average_invoice])
def test_reports_refuse_mixed_currencies(report):
    with pytest.raises(ValueError) as caught:
        report(MIXED)
    assert "EUR" in str(caught.value) and "USD" in str(caught.value)


def test_reports_work_on_one_currency_that_is_not_usd():
    batch = [inv("1", "acme", "100.00", "EUR"), inv("2", "globex", "50.00", "EUR")]
    assert revenue_by_region(batch) == {"OR": Decimal("150.00")}
    assert top_customers(batch, 1) == [("acme", Decimal("100.00"))]
    assert average_invoice(batch) == Decimal("75.00")
    assert average_invoice([]) == Decimal("0.00")
