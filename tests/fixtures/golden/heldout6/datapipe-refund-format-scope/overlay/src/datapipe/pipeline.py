"""The import pipeline: read an export, clean it, drop repeats, load it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from datapipe import db, readers, transforms
from datapipe.transforms import format_dollars


@dataclass(frozen=True)
class ImportSummary:
    rows_read: int
    duplicates: int  # rows repeating an order_id seen earlier in the same export
    inserted: int
    already_present: int  # orders the database already had
    total_cents: int = 0  # sum of the export's amounts, duplicates dropped, refunds negative

    def describe(self) -> str:
        return (
            f"read {self.rows_read} row(s): {self.inserted} inserted, "
            f"{self.duplicates} duplicate(s) dropped, {self.already_present} already present; "
            f"total {format_dollars(self.total_cents)}"
        )


def run(csv_path: str | Path, db_path: str | Path) -> ImportSummary:
    """Load the export at ``csv_path`` into the database at ``db_path``."""
    rows = readers.read_csv(csv_path)
    cleaned = transforms.clean_rows(rows)
    unique = transforms.dedupe(cleaned)
    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        inserted = db.insert_orders(conn, unique)
        db.record_import(conn, Path(csv_path).name, len(rows), inserted)
    finally:
        conn.close()
    return ImportSummary(
        rows_read=len(rows),
        duplicates=len(cleaned) - len(unique),
        inserted=inserted,
        already_present=len(unique) - inserted,
        total_cents=sum(row["amount_cents"] for row in unique),
    )
