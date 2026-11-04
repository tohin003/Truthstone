"""Customer statements: a customer's invoices, oldest first, and the balance.

Statements are printed and posted to customers. Their layout is signed off by finance.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from ledger.invoice import Invoice
from ledger.money import format_money


def _fmt_date(day: date | None) -> str:
    # Copied from export.py: customers read dates as DD/MM/YYYY.
    return day.strftime("%d/%m/%Y") if day else ""


def statement(customer: str, invoices: Iterable[Invoice], as_of: date) -> str:
    """The printed statement for ``customer``: one line per invoice, then the balance."""
    mine = sorted(
        (invoice for invoice in invoices if invoice.customer == customer),
        key=lambda invoice: (invoice.issued_on or date.min, invoice.number),
    )
    lines = [f"Statement for {customer}", f"As of {_fmt_date(as_of)}", ""]
    balance = Decimal("0")
    for invoice in mine:
        total = invoice.total()
        balance += total
        lines.append(f"{_fmt_date(invoice.issued_on):<10}  {invoice.number:<8}  {format_money(total):>10}")
    lines += ["", f"Balance: {format_money(balance)}"]
    return "\n".join(lines) + "\n"
