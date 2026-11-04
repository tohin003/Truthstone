"""Payment reminders (dunning letters) for unpaid invoices.

Letters are printed and posted to customers. Their wording and layout are signed off by
finance.
"""

from __future__ import annotations

from datetime import date

from ledger.invoice import Invoice
from ledger.money import format_money

HEADINGS = {1: "Payment reminder", 2: "Second reminder", 3: "Final notice"}


def _fmt_date(day: date | None) -> str:
    # Copied from export.py: customers read dates as DD/MM/YYYY.
    return day.strftime("%d/%m/%Y") if day else ""


def reminder(invoice: Invoice, today: date, level: int = 1) -> str:
    """The text of a reminder letter for ``invoice``. ``level`` is 1, 2 or 3."""
    if level not in HEADINGS:
        raise ValueError(f"level must be 1, 2 or 3, got {level!r}")
    return (
        f"{HEADINGS[level]}, {_fmt_date(today)}\n"
        "\n"
        f"Dear {invoice.customer},\n"
        "\n"
        f"our invoice {invoice.number} of {_fmt_date(invoice.issued_on)} for "
        f"{format_money(invoice.total())} is still unpaid.\n"
    )
