"""Monthly customer statements as plain-text files.

    PYTHONPATH=src python -m ledger.statements 2026-10 [--data data/invoices.json] [--out statements]

writes one statement per customer with invoices in that month, to
``statements/<customer>-<YYYY>-<MM>.txt``. The invoices come from ``data/invoices.json``.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem
from ledger.money import format_money

DATA = Path("data/invoices.json")
OUT = Path("statements")


def load(path: str | Path = DATA) -> dict[str, list[Invoice]]:
    """Invoices by month (``YYYY-MM``), in file order."""
    by_month: dict[str, list[Invoice]] = defaultdict(list)
    for raw in json.loads(Path(path).read_text(encoding="utf-8")):
        items = [LineItem(i["sku"], i["description"], i["quantity"], Decimal(i["unit_price"])) for i in raw["items"]]
        codes = [parse_code(code) for code in raw.get("discounts", [])]
        by_month[raw["month"]].append(Invoice(raw["number"], raw["customer"], raw["region"], items, codes))
    return dict(by_month)


def render(customer: str, month: str, invoices: list[Invoice]) -> str:
    lines = [f"Statement for {customer}, {month}", ""]
    for invoice in invoices:
        lines.append(f"  {invoice.number:<10} {format_money(invoice.total()):>12}")
    total = sum((invoice.total() for invoice in invoices), Decimal("0"))
    lines += ["", f"  {'Total due':<10} {format_money(total):>12}", ""]
    return "\n".join(lines)


def statement_path(out_dir: str | Path, customer: str, month: str) -> Path:
    return Path(out_dir) / f"{customer}-{month}.txt"


def write_month(month: str, data: str | Path = DATA, out_dir: str | Path = OUT) -> list[Path]:
    """Write every customer's statement for ``month``; return the paths written."""
    by_customer: dict[str, list[Invoice]] = defaultdict(list)
    for invoice in load(data).get(month, []):
        by_customer[invoice.customer].append(invoice)
    written = []
    for customer in sorted(by_customer):
        path = statement_path(out_dir, customer, month)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(customer, month, by_customer[customer]), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ledger.statements")
    parser.add_argument("month", help="YYYY-MM")
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    for path in write_month(args.month, args.data, args.out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
