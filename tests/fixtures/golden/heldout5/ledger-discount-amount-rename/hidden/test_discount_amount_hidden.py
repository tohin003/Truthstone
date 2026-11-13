from decimal import Decimal

from ledger.discounts import parse_code
from ledger.export import to_csv, to_row
from ledger.invoice import Invoice, LineItem
from ledger.statement import render


def discounted(codes=("SAVE10",), region="CA"):
    return Invoice(
        "INV-7",
        "acme",
        region,
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code(code) for code in codes],
    )


def test_discount_amount_replaces_discount_total():
    invoice = discounted()
    assert invoice.discount_amount() == Decimal("5.50")
    assert not hasattr(invoice, "discount_total")
    assert invoice.taxable() == Decimal("49.47")
    assert invoice.total() == Decimal("53.06")


def test_export_keeps_its_discount_column():
    row = to_row(discounted(region="OR"))
    assert row["discount"] == "5.50"
    assert to_csv([discounted(region="OR")]).splitlines()[0] == "number,customer,region,subtotal,discount,tax,total"


def test_statement_of_a_discounted_invoice():
    assert render(discounted()) == (
        "Statement for acme\n"
        "Invoice INV-7\n"
        "  Subtotal        $54.97\n"
        "  Discount         $5.50\n"
        "  Tax              $3.59\n"
        "  Total           $53.06\n"
    )


def test_statement_without_discounts_is_unchanged():
    invoice = Invoice("INV-3", "initech", "NY", [LineItem("W-1", "Widget", 4, Decimal("12.50"))])
    assert "Discount" not in render(invoice)
    assert render(invoice).endswith("  Total           $52.00\n")
