"""Discount codes.

``SAVE<n>`` takes n percent off; ``OFF<n>`` takes n currency units off. Percentage
discounts apply first, then fixed ones. However they combine, the total discount never
exceeds ``MAX_PERCENT`` percent of the subtotal and never makes it negative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ledger.money import quantize

MAX_PERCENT = Decimal("50")

_CODE = re.compile(r"^(SAVE|OFF)(\d{1,3})$")


class InvalidCode(ValueError):
    """The text is not a discount code."""


@dataclass(frozen=True)
class Discount:
    kind: str  # "percent" | "fixed"
    value: Decimal
    code: str = ""


def parse_code(code: str) -> Discount:
    match = _CODE.match(code.strip().upper())
    if not match:
        raise InvalidCode(code)
    prefix, number = match.groups()
    kind = "percent" if prefix == "SAVE" else "fixed"
    return Discount(kind, Decimal(number), match.group(0))


def apply(subtotal: Decimal, discounts: list[Discount]) -> Decimal:
    """The total discount for ``subtotal``: percent first, then fixed, then capped."""
    ordered = sorted(discounts, key=lambda d: 0 if d.kind == "percent" else 1)
    remaining = subtotal
    total = Decimal("0")
    for discount in ordered:
        if discount.kind == "percent":
            amount = remaining * discount.value / 100
        else:
            amount = discount.value
        amount = max(Decimal("0"), min(amount, remaining))
        total += amount
        remaining -= amount
    cap = subtotal * MAX_PERCENT / 100
    return quantize(min(total, cap))
