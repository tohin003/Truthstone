"""Payment plans: an invoice total paid in monthly installments.

The rules are in docs/payment-plans.md (BILL-212).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ledger.money import quantize, to_decimal

MAX_INSTALLMENTS = 12


def split(total: Decimal, count: int) -> list[Decimal]:
    """The installment amounts for ``total`` paid in ``count`` parts."""
    if not 1 <= count <= MAX_INSTALLMENTS:
        raise ValueError(f"a payment plan has 1 to {MAX_INSTALLMENTS} installments, not {count}")
    share = quantize(to_decimal(total) / count)
    return [share] * count


def due_dates(first: date, count: int) -> list[date]:
    """The due date of each installment, the first on ``first``."""
    return [first + timedelta(days=30 * index) for index in range(count)]
