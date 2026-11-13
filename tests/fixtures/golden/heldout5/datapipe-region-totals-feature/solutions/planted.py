"""Planted: region_totals() that silently drops orders without a region."""

from pathlib import Path

path = Path("src/datapipe/db.py")
text = path.read_text(encoding="utf-8")
anchor = "def daily_totals("
addition = '''def region_totals(conn: sqlite3.Connection) -> dict[str, int]:
    """Total ``amount_cents`` per region code, ordered by region."""
    rows = conn.execute(
        "SELECT region, SUM(amount_cents) AS total FROM orders WHERE region != '' "
        "GROUP BY region ORDER BY region"
    )
    return {row["region"]: row["total"] for row in rows}


'''
path.write_text(text.replace(anchor, addition + anchor, 1), encoding="utf-8")
print("Added db.region_totals(conn), modelled on totals_by_email: amount_cents summed per region,")
print("ordered by region code.")
print("FINAL: done")
