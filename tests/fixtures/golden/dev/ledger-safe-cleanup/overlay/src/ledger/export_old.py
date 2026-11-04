"""The pre-0.4 CSV export: semicolon-separated, no discount or tax columns.

It was kept while the old reporting job still read this format. That job was retired in
0.4.0 and nothing imports this module any more; use ``ledger.export``.
"""

from __future__ import annotations

from collections.abc import Iterable

from ledger.invoice import Invoice

HEADER = "number;customer;region;total"


def to_csv(invoices: Iterable[Invoice]) -> str:
    lines = [HEADER]
    for invoice in invoices:
        lines.append(f"{invoice.number};{invoice.customer};{invoice.region};{invoice.total()}")
    return "\n".join(lines) + "\n"
