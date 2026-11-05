"""The import pipeline: read an export, clean it, drop repeats, load it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from datapipe import db, readers, transforms
from datapipe.config import ImportSettings


@dataclass(frozen=True)
class ImportSummary:
    rows_read: int
    duplicates: int  # rows repeating an order_id seen earlier in the same export
    inserted: int
    already_present: int  # orders the database already had

    def describe(self) -> str:
        return (
            f"read {self.rows_read} row(s): {self.inserted} inserted, "
            f"{self.duplicates} duplicate(s) dropped, {self.already_present} already present"
        )


def run(csv_path: str | Path, db_path: str | Path, settings: ImportSettings | None = None) -> ImportSummary:
    """Load the export at ``csv_path`` into the database at ``db_path``.

    ``settings`` (see ``datapipe.config``) supply a region for orders exported without one and
    the source name recorded in the import log; without them, the defaults apply.
    """
    settings = settings or ImportSettings()
    rows = readers.read_csv(csv_path)
    cleaned = transforms.clean_rows(rows)
    if settings.default_region:
        cleaned = [row if row["region"] else {**row, "region": settings.default_region} for row in cleaned]
    unique = transforms.dedupe(cleaned)
    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        inserted = db.insert_orders(conn, unique)
        db.record_import(conn, settings.source_name or Path(csv_path).name, len(rows), inserted)
    finally:
        conn.close()
    return ImportSummary(
        rows_read=len(rows),
        duplicates=len(cleaned) - len(unique),
        inserted=inserted,
        already_present=len(unique) - inserted,
    )
