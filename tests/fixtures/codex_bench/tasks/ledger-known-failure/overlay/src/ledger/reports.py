"""Revenue reports over a batch of invoices."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from ledger.invoice import Invoice
from ledger.money import quantize


def revenue_by_region(invoices: Iterable[Invoice]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        totals[invoice.region] += invoice.total()
    return dict(sorted(totals.items()))


def top_customers(invoices: Iterable[Invoice], n: int = 3) -> list[tuple[str, Decimal]]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        totals[invoice.customer] += invoice.total()
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:n]


def average_invoice(invoices: Iterable[Invoice]) -> Decimal:
    # LEDGER-142: product has not decided what an empty batch should report.
    batch = list(invoices)
    return quantize(sum((inv.total() for inv in batch), Decimal("0")) / len(batch))
