"""Cleaning steps between reading an export and loading it.

From here on amounts are integer cents, so totals never pick up floating-point error.

This module is shared with the billing service, which imports ``parse_amount`` and
``normalize_email`` and relies on them behaving exactly as they do here: a change to this file
needs billing's sign-off.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

_AMOUNT = re.compile(r"-?\d+(?:\.\d{1,2})?")


class TransformError(ValueError):
    """A value could not be cleaned."""


def normalize_email(email: str) -> str:
    """Trim and lowercase an address, so one customer always groups under one key."""
    cleaned = email.strip().lower()
    local, _, domain = cleaned.partition("@")
    if not local or "@" in domain or "." not in domain.strip("."):
        raise TransformError(f"not an email address: {email!r}")
    return cleaned


def parse_amount(text: str) -> int:
    """Read an amount such as ``"12.50"``, ``"$1,240.00"`` or ``"-3"`` as integer cents."""
    cleaned = text.strip().replace("$", "", 1).replace(",", "")
    if not _AMOUNT.fullmatch(cleaned):
        raise TransformError(f"not an amount: {text!r}")
    return int(Decimal(cleaned) * 100)


def clean_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise emails, turn ``amount`` into ``amount_cents`` and fill optional columns.

    The input rows are not modified.
    """
    cleaned = []
    for row in rows:
        out = {key: value for key, value in row.items() if key != "amount"}
        out["email"] = normalize_email(row["email"])
        out["amount_cents"] = parse_amount(row["amount"])
        out.setdefault("quantity", 1)
        out.setdefault("region", "")
        cleaned.append(out)
    return cleaned


def dedupe(rows: Iterable[dict[str, Any]], key: str = "order_id") -> list[dict[str, Any]]:
    """Keep the first row for each value of ``key``, in order; drop the rest."""
    seen: set[Any] = set()
    unique = []
    for row in rows:
        if row[key] in seen:
            continue
        seen.add(row[key])
        unique.append(row)
    return unique


def group_totals(rows: Iterable[dict[str, Any]], key: str) -> dict[Any, int]:
    """Sum ``amount_cents`` for each value of ``key``, ordered by key."""
    totals: dict[Any, int] = defaultdict(int)
    for row in rows:
        totals[row[key]] += row["amount_cents"]
    return dict(sorted(totals.items()))
