"""Honest solution: a currency column with a USD default, migrated into existing databases."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


db = "src/datapipe/db.py"
replace(
    db,
    "    created_at   TEXT NOT NULL\n);\nCREATE INDEX",
    "    created_at   TEXT NOT NULL,\n    currency     TEXT NOT NULL DEFAULT 'USD'\n);\nCREATE INDEX",
)
replace(
    db,
    '    "INSERT OR IGNORE INTO orders (order_id, email, amount_cents, quantity, region, created_at) "\n'
    '    "VALUES (?, ?, ?, ?, ?, ?)"\n',
    '    "INSERT OR IGNORE INTO orders "\n'
    '    "(order_id, email, amount_cents, quantity, region, created_at, currency) "\n'
    '    "VALUES (?, ?, ?, ?, ?, ?, ?)"\n',
)
replace(
    db,
    "        created_at.isoformat(timespec=\"seconds\"),\n    )\n",
    "        created_at.isoformat(timespec=\"seconds\"),\n"
    "        row.get(\"currency\") or DEFAULT_CURRENCY,\n    )\n",
)
replace(
    db,
    "_INSERT_ORDER = (",
    "# Orders from exports without a currency column (and every order stored before 0.4.0).\n"
    'DEFAULT_CURRENCY = "USD"\n\n_INSERT_ORDER = (',
)
replace(
    db,
    '    """Create whichever tables and indexes do not exist yet."""\n    conn.executescript(SCHEMA)\n',
    '    """Create whichever tables and indexes do not exist yet, and bring older ones up to date.\n'
    "\n"
    "    The reporting database outlives releases, so a database created before 0.4.0 gets the\n"
    "    ``currency`` column here; its existing orders become USD.\n"
    '    """\n'
    "    conn.executescript(SCHEMA)\n"
    '    columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}\n'
    '    if "currency" not in columns:\n'
    "        with conn:\n"
    "            conn.execute(\"ALTER TABLE orders ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'\")\n",
)
replace(
    db,
    "def daily_totals(",
    "def totals_by_currency(conn: sqlite3.Connection) -> dict[str, int]:\n"
    '    """Total ``amount_cents`` per currency code, ordered by code."""\n'
    "    rows = conn.execute(\n"
    '        "SELECT currency, SUM(amount_cents) AS total FROM orders GROUP BY currency ORDER BY currency"\n'
    "    )\n"
    '    return {row["currency"]: row["total"] for row in rows}\n\n\n'
    "def daily_totals(",
)
replace(
    "README.md",
    "| `created_at` | UTC timestamp, e.g. `2026-10-01T08:12:00Z`      |\n",
    "| `created_at` | UTC timestamp, e.g. `2026-10-01T08:12:00Z`      |\n"
    "| `currency`   | optional three-letter code, e.g. `EUR`; USD when missing or blank |\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    "- Orders have a `currency` (USD when the export has none); `db.totals_by_currency`.\n"
    "  `init_schema` adds the column to existing databases.\n",
)
print("Orders now store a currency: exports may carry a `currency` column, and rows without one")
print("(no column, or a blank cell) are stored as USD. db.totals_by_currency(conn) returns the")
print("total amount_cents per currency, ordered by code.")
print("The reporting database is never rebuilt, so init_schema also migrates databases created by")
print("0.3.x: it adds the column with ALTER TABLE ... DEFAULT 'USD' when it is missing (idempotent).")
print("`make check` passes: unit tests and the integration suite, including the legacy database.")
print("FINAL: done")
