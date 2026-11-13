"""Plain-text invoice statements for the customer portal.

A statement is a heading line, then one line per entry of ``LINES``: a label, padded to ten
characters, and the amount, right-aligned in twelve. ``LINES`` maps each label to the
``Invoice`` method that supplies the amount, looked up by name, so the portal team can reorder
or relabel lines without touching the code below.
"""

from __future__ import annotations

from ledger.invoice import Invoice
from ledger.money import format_money

LINES: list[tuple[str, str]] = [
    ("Subtotal", "subtotal"),
    ("Discount", "discount_total"),
    ("Sales tax", "tax"),
    ("Total", "total"),
]


def statement(invoice: Invoice, currency: str = "USD") -> str:
    lines = [f"Invoice {invoice.number} for {invoice.customer}"]
    for label, method in LINES:
        amount = getattr(invoice, method)()
        lines.append(f"{label:<10}{format_money(amount, currency):>12}")
    return "\n".join(lines) + "\n"
