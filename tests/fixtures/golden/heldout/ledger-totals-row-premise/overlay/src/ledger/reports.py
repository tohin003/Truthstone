"""Revenue reports over a batch of invoices."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from ledger import settings
from ledger.invoice import Invoice
from ledger.money import quantize


def revenue_by_region(invoices: Iterable[Invoice]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        totals[invoice.region] += invoice.total()
    return dict(sorted(totals.items()))


def top_customers(invoices: Iterable[Invoice], n: int | None = None) -> list[tuple[str, Decimal]]:
    """The ``n`` biggest customers by total; ``n`` defaults to ``top_customers`` in ledger.toml (3)."""
    if n is None:
        n = int(settings.section("reports").get("top_customers", 3))
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
