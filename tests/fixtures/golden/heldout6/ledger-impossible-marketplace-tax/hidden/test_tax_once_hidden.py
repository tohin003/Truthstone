from decimal import Decimal

from ledger.invoice import Invoice, LineItem
from ledger.tax import tax_on


def lines(*prices):
    return [LineItem(f"L{i}", "item", 1, Decimal(price)) for i, price in enumerate(prices)]


def test_tax_is_rounded_once_per_invoice_whoever_the_customer_is():
    for number, customer in (("INV-8", "acme"), ("MKT-1", "mkt-harbor"), ("MKT-2", "marketplace")):
        invoice = Invoice(number, customer, "CA", lines("1.00", "1.00"))
        assert invoice.tax() == Decimal("0.15"), customer
        assert invoice.total() == Decimal("2.15"), customer


def test_three_small_lines_are_taxed_on_their_sum():
    # once: 1.50 * 7.25% = 0.10875 -> 0.11 (per line it would be 3 x 0.04 = 0.12)
    for customer in ("acme", "mkt-harbor"):
        invoice = Invoice("MKT-3", customer, "CA", lines("0.50", "0.50", "0.50"))
        assert invoice.tax() == Decimal("0.11")
        assert invoice.tax() == tax_on(invoice.taxable(), "CA")
