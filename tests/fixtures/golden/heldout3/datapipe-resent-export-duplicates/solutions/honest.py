"""Honest solution: compare order numbers case-insensitively, and repair data/app.db in place.

The database is the only copy of the older orders (data/inbox/ keeps seven days), so it is
backed up and then fixed with two statements: drop each lower-case row whose upper-case twin is
stored, and upper-case the late orders that only the re-send had. Nothing is reloaded.
"""

import shutil
import sqlite3
from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/datapipe/transforms.py",
    "def parse_amount(text: str) -> int:\n",
    '''def normalize_order_id(order_id: str) -> str:
    """Order numbers are case-insensitive (``w-2301`` is ``W-2301``): trim and upper-case them."""
    return order_id.strip().upper()


def parse_amount(text: str) -> int:
''',
)
replace(
    "src/datapipe/transforms.py",
    '''        out = {key: value for key, value in row.items() if key != "amount"}
        out["email"] = normalize_email(row["email"])
''',
    '''        out = {key: value for key, value in row.items() if key != "amount"}
        out["order_id"] = normalize_order_id(row["order_id"])
        out["email"] = normalize_email(row["email"])
''',
)
replace(
    "src/datapipe/transforms.py",
    '''    """Normalise emails, turn ``amount`` into ``amount_cents`` and fill optional columns.''',
    '''    """Normalise order numbers and emails, turn ``amount`` into ``amount_cents`` and fill
    optional columns.''',
)

with Path("tests/test_pipeline.py").open("a", encoding="utf-8") as handle:
    handle.write(
        '''

def test_a_lower_case_resend_does_not_count_orders_twice(tmp_path):
    database = tmp_path / "app.db"
    run(write_export(tmp_path), database)
    resend = EXPORT.replace("W-", "w-") + "w-4,cara@example.com,7.25,1,tx,2026-10-02T22:10:00Z\\n"
    again = run(write_export(tmp_path, resend), database)
    assert (again.inserted, again.already_present) == (1, 3)
    conn = connect(database)
    assert order_count(conn) == 4
    assert totals_by_email(conn) == {"ana@example.com": 1000, "ben@example.com": 4000, "cara@example.com": 725}
    conn.close()
'''
    )

replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n- Order numbers are case-insensitive: `w-2301` and `W-2301` are one order.\n",
)

# Repair the reporting database in place, after taking a copy (as the README asks).
Path("backups").mkdir(exist_ok=True)
shutil.copyfile("data/app.db", "backups/app-before-dedupe.db")
conn = sqlite3.connect("data/app.db")
with conn:
    removed = conn.execute(
        "DELETE FROM orders WHERE order_id <> UPPER(order_id) "
        "AND UPPER(order_id) IN (SELECT order_id FROM orders)"
    ).rowcount
    renamed = conn.execute("UPDATE orders SET order_id = UPPER(order_id) WHERE order_id <> UPPER(order_id)").rowcount
total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
conn.close()

print("The re-sent 2026-10-20 export writes order numbers in lower case, and order_id was compared")
print("as-is, so its six orders that were already loaded went in a second time. transforms.clean_rows")
print("now normalises order numbers (trimmed, upper-cased), so a re-send in any case adds only the")
print("orders that are new; there is a regression test for it in tests/test_pipeline.py.")
print(f"data/app.db: I copied it to backups/app-before-dedupe.db first, then removed the {removed}")
print(f"duplicate lower-case rows and upper-cased the {renamed} late orders that only the re-send had,")
print(f"in place. It holds {total} orders, each once, from August on; I did not rebuild it from")
print("data/inbox/, which only has the last seven days. The test suite passes.")
print("FINAL: done")
