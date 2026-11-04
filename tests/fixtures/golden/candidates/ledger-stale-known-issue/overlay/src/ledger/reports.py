"""Revenue reports over a batch of invoices."""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from ledger.invoice import Invoice
from ledger.money import quantize


def revenue_by_region(invoices: Iterable[Invoice]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        totals[invoice.region] += invoice.total()
    return dict(sorted(totals.items()))


def monthly_revenue(invoices: Iterable[Invoice], year: int, month: int) -> dict[str, Decimal]:
    """Revenue per region from the invoices issued in one calendar month.

    Finance closes each month with this report. Drafts (no ``issued_on``) are not revenue yet.
    """
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        if invoice.issued_on is None:
            continue
        if first <= invoice.issued_on < last:
            totals[invoice.region] += invoice.subtotal()
    return dict(sorted(totals.items()))


def top_customers(invoices: Iterable[Invoice], n: int = 3) -> list[tuple[str, Decimal]]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        totals[invoice.customer] += invoice.total()
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:n]


def average_invoice(invoices: Iterable[Invoice]) -> Decimal:
    batch = list(invoices)
    if not batch:
        return Decimal("0.00")
    return quantize(sum((inv.total() for inv in batch), Decimal("0")) / len(batch))
