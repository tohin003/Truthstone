from decimal import Decimal

from ledger.export_old import to_csv
from ledger.invoice import Invoice, LineItem


def test_old_export_format():
    invoice = Invoice("INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])
    assert to_csv([invoice]).splitlines() == [
        "number;customer;region;total",
        "INV-9;globex;NY;20.80",
    ]
