"""Plain-text customer statements, as printed on the monthly mailing.

``LINES`` lists each amount line: its label, the ``Invoice`` method that supplies the amount, and
whether the line is printed only for invoices that carry discount codes.
"""

from __future__ import annotations

from ledger.invoice import Invoice
from ledger.money import format_money

LINES: list[tuple[str, str, bool]] = [
    ("Subtotal", "subtotal", False),
    ("Discount", "discount_total", True),
    ("Tax", "tax", False),
    ("Total", "total", False),
]


def render(invoice: Invoice, currency: str = "USD") -> str:
    lines = [f"Statement for {invoice.customer}", f"Invoice {invoice.number}"]
    for label, method, discounted_only in LINES:
        if discounted_only and not invoice.discounts:
            continue
        amount = getattr(invoice, method)()
        lines.append(f"  {label:<10}{format_money(amount, currency):>12}")
    return "\n".join(lines) + "\n"
