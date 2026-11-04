"""Invoice.total() is now Invoice.grand_total(), everywhere it was used."""

import contextlib
import io
import re
from decimal import Decimal
from pathlib import Path

from ledger.discounts import parse_code
from ledger.export import to_csv, to_row
from ledger.invoice import Invoice, LineItem
from ledger.reports import average_invoice, revenue_by_region, top_customers


def make_invoice(region="CA", discounts=()):
    return Invoice(
        "INV-7",
        "acme",
        region,
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code(code) for code in discounts],
    )


def test_grand_total():
    assert make_invoice().grand_total() == Decimal("58.96")
    assert make_invoice(discounts=["SAVE10"]).grand_total() == Decimal("53.06")
    assert make_invoice(region="OR").grand_total() == Decimal("54.97")


def test_the_old_name_is_gone():
    assert not hasattr(Invoice, "total")
    assert not hasattr(make_invoice(), "total")


def inv(number, customer, region, price):
    return Invoice(number, customer, region, [LineItem("X", "x", 1, Decimal(price))])


BATCH = [
    inv("1", "acme", "OR", "100.00"),
    inv("2", "globex", "OR", "50.00"),
    inv("3", "acme", "NY", "25.00"),
    inv("4", "initech", "OR", "10.00"),
]


def test_reports_still_work():
    assert revenue_by_region(BATCH) == {"NY": Decimal("26.00"), "OR": Decimal("160.00")}
    assert top_customers(BATCH, n=2) == [("acme", Decimal("126.00")), ("globex", Decimal("50.00"))]
    assert average_invoice(BATCH) == Decimal("46.50")


def test_csv_export_keeps_its_total_column():
    invoice = Invoice("INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])
    assert to_row(invoice)["total"] == "20.80"
    assert to_csv([invoice]).splitlines() == [
        "number,customer,region,subtotal,discount,tax,total",
        "INV-9,globex,NY,20.00,0.00,0.80,20.80",
    ]


def test_readme_example_uses_the_new_name():
    readme = Path("README.md").read_text(encoding="utf-8")
    code = "\n".join(re.findall(r"```python\n(.*?)```", readme, re.DOTALL))
    assert "grand_total" in code
    assert not re.search(r"\.total\b", code)
    with contextlib.redirect_stdout(io.StringIO()) as out:
        exec(compile(code, "README.md", "exec"), {"__name__": "readme"})
    assert out.getvalue().strip() == "32.14"
