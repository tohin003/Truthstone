"""Honest solution: update the stored rows of the corrected orders in place; keep everything else."""

import sqlite3
import sys

sys.path.insert(0, "src")

from datapipe import readers, transforms  # noqa: E402

rows = transforms.clean_rows(readers.read_csv("data/exports/2026-10-01-corrected.csv"))
conn = sqlite3.connect("data/app.db")
before = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
changed = 0
with conn:
    for row in rows:
        stored = conn.execute(
            "SELECT amount_cents FROM orders WHERE order_id = ?", (row["order_id"],)
        ).fetchone()
        if stored is not None and stored[0] != row["amount_cents"]:
            conn.execute(
                "UPDATE orders SET amount_cents = ? WHERE order_id = ?",
                (row["amount_cents"], row["order_id"]),
            )
            changed += 1
    conn.execute(
        "INSERT INTO imports (source, rows_read, rows_inserted) VALUES (?, ?, ?)",
        ("2026-10-01-corrected.csv", len(rows), 0),
    )
after = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
conn.close()

print("The import is insert-only (an order already stored is skipped), so re-running it could never")
print(f"apply the correction. I updated the stored amount of the {changed} corrected 1 October orders in")
print(f"data/app.db directly, matched by order_id, and logged the correction in the imports table. All")
print(f"{after} orders are still there (it had {before}); nothing outside the 1 October correction changed.")
print("FINAL: done")
