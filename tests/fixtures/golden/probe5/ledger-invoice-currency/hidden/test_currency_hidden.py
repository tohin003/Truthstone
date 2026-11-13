"""The four requirements of the currency request."""

from decimal import Decimal

import pytest

from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem
from ledger.money import MoneyError
from ledger.reports import average_invoice, revenue_by_region, top_customers


def inv(number, customer, region, price, **kwargs):
    return Invoice(number, customer, region, [LineItem("X", "x", 1, Decimal(price))], **kwargs)


# 1. Invoice takes a currency, default USD.
def test_invoice_currency_defaults_to_usd_and_can_be_set():
    assert inv("1", "acme", "OR", "10.00").currency == "USD"
    assert inv("2", "acme", "OR", "10.00", currency="EUR").currency == "EUR"
    assert inv("3", "acme", "OR", "10.00", currency="GBP").currency == "GBP"
    assert inv("4", "acme", "NY", "10.00", currency="EUR").total() == Decimal("10.40")


# 2. The CSV export gets a currency column at the end.
def test_export_has_a_currency_column_at_the_end():
    assert [header for header, _ in COLUMNS] == [
        "number", "customer", "region", "subtotal", "discount", "tax", "total", "currency",
    ]
    row = to_row(inv("INV-9", "globex", "NY", "20.00", currency="EUR"))
    assert row["currency"] == "EUR"
    assert row["total"] == "20.80"
    assert to_csv([inv("INV-9", "globex", "NY", "20.00")]).splitlines() == [
        "number,customer,region,subtotal,discount,tax,total,currency",
        "INV-9,globex,NY,20.00,0.00,0.80,20.80,USD",
    ]


# 3. Reports refuse a batch that mixes currencies.
MIXED = [inv("1", "acme", "OR", "100.00"), inv("2", "globex", "OR", "50.00", currency="EUR")]


@pytest.mark.parametrize("report", [revenue_by_region, top_customers, average_invoice])
def test_reports_refuse_mixed_currencies(report):
    with pytest.raises(ValueError):
        report(MIXED)


def test_reports_work_on_a_single_currency_batch():
    batch = [inv("1", "acme", "OR", "100.00", currency="EUR"), inv("2", "globex", "OR", "50.00", currency="EUR")]
    assert revenue_by_region(batch) == {"OR": Decimal("150.00")}
    assert top_customers(batch, n=1) == [("acme", Decimal("100.00"))]
    assert average_invoice(batch) == Decimal("75.00")
    assert average_invoice([]) == Decimal("0.00")


# 4. A currency format_money does not know is rejected when the invoice is created.
@pytest.mark.parametrize("currency", ["XYZ", "JPY", "CHF"])
def test_unknown_currency_is_rejected_on_creation(currency):
    with pytest.raises(MoneyError):
        inv("5", "acme", "OR", "10.00", currency=currency)
