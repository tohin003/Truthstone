import json

from ledger.statements import main, render, write_month
from ledger.invoice import Invoice, LineItem
from decimal import Decimal

DATA = [
    {"number": "INV-1", "month": "2026-10", "customer": "acme", "region": "OR",
     "items": [{"sku": "W-1", "description": "Widget", "quantity": 2, "unit_price": "10.00"}]},
    {"number": "INV-2", "month": "2026-10", "customer": "globex", "region": "OR",
     "items": [{"sku": "W-1", "description": "Widget", "quantity": 1, "unit_price": "5.00"}]},
    {"number": "INV-3", "month": "2026-09", "customer": "acme", "region": "OR",
     "items": [{"sku": "W-1", "description": "Widget", "quantity": 1, "unit_price": "1.00"}]},
]  # fmt: skip


def data_file(tmp_path):
    path = tmp_path / "invoices.json"
    path.write_text(json.dumps(DATA), encoding="utf-8")
    return path


def test_render():
    invoice = Invoice("INV-1", "acme", "OR", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])
    text = render("acme", "2026-10", [invoice])
    assert text.splitlines()[0] == "Statement for acme, 2026-10"
    assert "INV-1" in text and "$20.00" in text


def test_write_month_writes_one_statement_per_customer(tmp_path):
    written = write_month("2026-10", data_file(tmp_path), tmp_path / "out")
    assert len(written) == 2 and all(path.is_file() for path in written)
    assert "Statement for acme, 2026-10" in written[0].read_text(encoding="utf-8")


def test_cli(tmp_path, capsys):
    assert main(["2026-09", "--data", str(data_file(tmp_path)), "--out", str(tmp_path / "out")]) == 0
    assert capsys.readouterr().out.count(".txt") == 1
