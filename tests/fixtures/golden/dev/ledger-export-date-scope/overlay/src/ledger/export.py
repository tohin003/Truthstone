"""CSV export of invoices, read by the accounting system's import.

``COLUMNS`` maps each CSV header to the ``Invoice`` attribute that supplies it. Methods
are called; plain attributes are read.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date

from ledger.invoice import Invoice
from ledger.money import quantize

COLUMNS: list[tuple[str, str]] = [
    ("number", "number"),
    ("issued", "issued_on"),
    ("customer", "customer"),
    ("region", "region"),
    ("subtotal", "subtotal"),
    ("discount", "discount_total"),
    ("tax", "tax"),
    ("total", "total"),
]


def _fmt_date(day: date | None) -> str:
    # TODO: statements.py and dunning.py each carry a copy of this helper; fold the three
    # copies into one shared function some day.
    return day.strftime("%d/%m/%Y") if day else ""


def _cell(value: object) -> str:
    if value is None or isinstance(value, date):
        return _fmt_date(value)
    if isinstance(value, str):
        return value
    return str(quantize(value))


def to_row(invoice: Invoice) -> dict[str, str]:
    row: dict[str, str] = {}
    for header, attribute in COLUMNS:
        value = getattr(invoice, attribute)
        if callable(value):
            value = value()
        row[header] = _cell(value)
    return row


def to_csv(invoices: Iterable[Invoice]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[header for header, _ in COLUMNS], lineterminator="\n")
    writer.writeheader()
    for invoice in invoices:
        writer.writerow(to_row(invoice))
    return buffer.getvalue()
