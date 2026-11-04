"""CSV export of invoices.

``COLUMNS`` maps each CSV header to the ``Invoice`` attribute that supplies it. Methods
are called; plain attributes are read. The column separator is ``delimiter`` under
``[export]`` in ledger.toml (default ``,``).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from ledger import settings
from ledger.invoice import Invoice
from ledger.money import quantize

COLUMNS: list[tuple[str, str]] = [
    ("number", "number"),
    ("customer", "customer"),
    ("region", "region"),
    ("subtotal", "subtotal"),
    ("discount", "discount_total"),
    ("tax", "tax"),
    ("total", "total"),
]


def to_row(invoice: Invoice) -> dict[str, str]:
    row: dict[str, str] = {}
    for header, attribute in COLUMNS:
        value = getattr(invoice, attribute)
        if callable(value):
            value = value()
        row[header] = str(quantize(value)) if not isinstance(value, str) else value
    return row


def to_csv(invoices: Iterable[Invoice]) -> str:
    delimiter = settings.section("export").get("delimiter", ",")
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=[header for header, _ in COLUMNS], delimiter=delimiter, lineterminator="\n"
    )
    writer.writeheader()
    for invoice in invoices:
        writer.writerow(to_row(invoice))
    return buffer.getvalue()
