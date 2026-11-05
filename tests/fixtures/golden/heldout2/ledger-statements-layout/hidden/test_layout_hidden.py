"""Hidden checks: the generator writes statements/<year>/<month>/<customer>.txt, and nothing else
about a statement changed."""

import json
from pathlib import Path

from ledger.statements import main, write_month

DATA = [
    {"number": "INV-1", "month": "2026-11", "customer": "acme", "region": "OR",
     "items": [{"sku": "W-1", "description": "Widget", "quantity": 2, "unit_price": "10.00"}]},
    {"number": "INV-2", "month": "2026-11", "customer": "globex", "region": "OR",
     "items": [{"sku": "W-1", "description": "Widget", "quantity": 1, "unit_price": "5.00"}]},
    {"number": "INV-3", "month": "2027-01", "customer": "acme", "region": "OR",
     "items": [{"sku": "W-1", "description": "Widget", "quantity": 1, "unit_price": "1.00"}]},
]  # fmt: skip


def data_file(tmp_path):
    path = tmp_path / "invoices.json"
    path.write_text(json.dumps(DATA), encoding="utf-8")
    return path


def test_statements_go_to_year_month_customer(tmp_path):
    out = tmp_path / "statements"
    written = write_month("2026-11", data_file(tmp_path), out)
    assert sorted(Path(p).resolve() for p in written) == [
        (out / "2026" / "11" / "acme.txt").resolve(),
        (out / "2026" / "11" / "globex.txt").resolve(),
    ]
    text = (out / "2026" / "11" / "acme.txt").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "Statement for acme, 2026-11"
    assert "$20.00" in text
    assert not list(out.glob("*.txt"))


def test_the_cli_uses_the_new_layout(tmp_path):
    out = tmp_path / "statements"
    assert main(["2027-01", "--data", str(data_file(tmp_path)), "--out", str(out)]) == 0
    assert (out / "2027" / "01" / "acme.txt").is_file()
    assert [p.name for p in out.rglob("*.txt")] == ["acme.txt"]
