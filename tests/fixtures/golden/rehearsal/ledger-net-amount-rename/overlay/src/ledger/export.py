"""CSV export of invoices.

``COLUMNS`` maps each CSV header to the ``Invoice`` attribute that supplies it. Methods
are called; plain attributes are read. Other exports use a *profile*: a JSON file in
``ledger/profiles/`` that lists its columns the same way (``{"header": ..., "source": ...}``,
the source being an ``Invoice`` attribute or method), selected with
``to_csv(invoices, profile="<name>")``.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from ledger.invoice import Invoice
from ledger.money import quantize

PROFILES = Path(__file__).with_name("profiles")

COLUMNS: list[tuple[str, str]] = [
    ("number", "number"),
    ("customer", "customer"),
    ("region", "region"),
    ("subtotal", "subtotal"),
    ("discount", "discount_total"),
    ("tax", "tax"),
    ("total", "total"),
]


def load_profile(name: str) -> list[tuple[str, str]]:
    """The (header, source) columns of the export profile ``profiles/<name>.json``."""
    data = json.loads((PROFILES / f"{name}.json").read_text(encoding="utf-8"))
    return [(column["header"], column["source"]) for column in data["columns"]]


def to_row(invoice: Invoice, columns: Sequence[tuple[str, str]] = COLUMNS) -> dict[str, str]:
    row: dict[str, str] = {}
    for header, attribute in columns:
        value = getattr(invoice, attribute)
        if callable(value):
            value = value()
        row[header] = str(quantize(value)) if not isinstance(value, str) else value
    return row


def to_csv(invoices: Iterable[Invoice], profile: str | None = None) -> str:
    columns = COLUMNS if profile is None else load_profile(profile)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[header for header, _ in columns], lineterminator="\n")
    writer.writeheader()
    for invoice in invoices:
        writer.writerow(to_row(invoice, columns))
    return buffer.getvalue()
