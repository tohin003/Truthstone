"""The default export is still byte-for-byte ERP import format v1.9."""

from decimal import Decimal

from ledger.discounts import parse_code
from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem

V19 = (
    "number,customer,subtotal,discount,tax,total\n"
    "INV-1001,acme,54.97,5.50,3.59,53.06\n"
    "INV-1002,globex,20.00,0.00,0.80,20.80\n"
    "INV-1003,initech,100.00,0.00,0.00,100.00\n"
)


def batch():
    return [
        Invoice(
            "INV-1001", "acme", "CA",
            [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
            [parse_code("SAVE10")],
        ),
        Invoice("INV-1002", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))]),
        Invoice("INV-1003", "initech", "OR", [LineItem("S-9", "Service", 1, Decimal("100.00"))]),
    ]


def test_the_export_is_byte_for_byte_v19():
    assert to_csv(batch()).encode("utf-8") == V19.encode("utf-8")


def test_the_layout_is_unchanged():
    assert [header for header, _ in COLUMNS] == ["number", "customer", "subtotal", "discount", "tax", "total"]
    assert list(to_row(batch()[0])) == ["number", "customer", "subtotal", "discount", "tax", "total"]


def test_an_empty_export_is_just_the_header():
    assert to_csv([]) == "number,customer,subtotal,discount,tax,total\n"
