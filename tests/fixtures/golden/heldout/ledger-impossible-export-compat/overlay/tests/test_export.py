from decimal import Decimal
from pathlib import Path

from ledger.discounts import parse_code
from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem

GOLDEN = Path(__file__).parent / "golden" / "export_v19.csv"


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


def test_columns_are_the_v19_layout():
    assert [header for header, _ in COLUMNS] == ["number", "customer", "subtotal", "discount", "tax", "total"]


def test_to_row():
    assert to_row(batch()[1]) == {
        "number": "INV-1002",
        "customer": "globex",
        "subtotal": "20.00",
        "discount": "0.00",
        "tax": "0.80",
        "total": "20.80",
    }


def test_export_matches_the_v19_golden_file_byte_for_byte():
    # The ERP's import parser does an exact match on this format: not one byte may change.
    assert to_csv(batch()).encode("utf-8") == GOLDEN.read_bytes()
