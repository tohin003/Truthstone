"""Money helpers, vendored from the billing service (billing-core 2.4.1).

DO NOT EDIT THIS COPY. It is replaced wholesale on every billing-core upgrade, so a local change
is silently lost, and billing's invoice and ledger code relies on ``split_cents`` behaving exactly
as it does there. Problems go to the billing team, upstream.
"""

from __future__ import annotations


def split_cents(cents: int) -> tuple[int, int]:
    """Split integer cents into whole units and the remaining cents: ``124050`` -> ``(1240, 50)``."""
    return divmod(cents, 100)


def to_cents(units: int, cents: int = 0) -> int:
    """The inverse of ``split_cents``: ``to_cents(1240, 50)`` -> ``124050``."""
    return units * 100 + cents
