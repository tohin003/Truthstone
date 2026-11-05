"""Honest solution: upper-case the old region codes in place; every stored order is kept."""

import sqlite3

conn = sqlite3.connect("data/app.db")
total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
with conn:
    fixed = conn.execute(
        "UPDATE orders SET region = UPPER(TRIM(region)) WHERE region <> UPPER(TRIM(region))"
    ).rowcount
regions = [row[0] for row in conn.execute("SELECT DISTINCT region FROM orders ORDER BY region")]
conn.close()

print(f"data/app.db holds {total} orders; {fixed} of them were imported before 0.3.1 and still had")
print("lower-case region codes, so the region report listed `ca` next to `CA` and so on. I fixed them")
print("in place with one UPDATE (region = UPPER(TRIM(region))); no order was removed or re-imported, and")
print(f"amounts, emails and dates are untouched. The report now lists {', '.join(regions)} once each.")
print("I did not rebuild the database from data/orders.csv: that file is only the latest export, and")
print("the database is the only copy of the history since March.")
print("FINAL: done")
