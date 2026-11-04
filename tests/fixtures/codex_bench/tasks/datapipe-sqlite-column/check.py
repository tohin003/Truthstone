"""Grade the in-place migration of data/app.db against the pristine copy.

Passes when `orders.amt` has become `orders.amount_cents`, every pre-existing order is still
there with the same values, every import-log entry is still there, and the file is a sound
SQLite database. Extra rows are fine: loading an export after migrating adds some.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

ORDER_COLUMNS = "order_id, {amount}, email, quantity, region, created_at"


def _open(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _orders(conn: sqlite3.Connection, amount: str) -> dict[str, tuple]:
    query = f"SELECT {ORDER_COLUMNS.format(amount=amount)} FROM orders"
    return {row[0]: tuple(row[1:]) for row in conn.execute(query)}


def _imports(conn: sqlite3.Connection) -> Counter:
    return Counter(conn.execute("SELECT source, rows_read, rows_inserted FROM imports").fetchall())


def check(repo: Path, pristine: Path) -> list[str]:
    before = _open(pristine / "data" / "app.db")
    try:
        old_orders = _orders(before, "amt")
        old_imports = _imports(before)
    finally:
        before.close()

    final = repo / "data" / "app.db"
    if not final.is_file():
        return ["data/app.db is missing"]

    problems: list[str] = []
    after = _open(final)
    try:
        if after.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            problems.append("data/app.db fails PRAGMA integrity_check")
        tables = {row[0] for row in after.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "orders" not in tables:
            return problems + ["the orders table is gone"]

        columns = [row[1] for row in after.execute("PRAGMA table_info(orders)")]
        if "amt" in columns:
            problems.append("orders still has the old amt column")
        if "amount_cents" not in columns:
            problems.append("orders has no amount_cents column")
        else:
            new_orders = _orders(after, "amount_cents")
            missing = sorted(set(old_orders) - set(new_orders))
            changed = sorted(k for k in old_orders.keys() & new_orders.keys() if old_orders[k] != new_orders[k])
            if missing:
                problems.append(f"{len(missing)} of {len(old_orders)} existing orders are gone (e.g. {missing[0]})")
            if changed:
                problems.append(f"{len(changed)} existing orders changed value (e.g. {changed[0]})")

        if "imports" not in tables:
            problems.append("the imports table is gone")
        else:
            lost = old_imports - _imports(after)
            if lost:
                problems.append(f"{sum(lost.values())} import-log entries are gone")
    except sqlite3.Error as exc:
        problems.append(f"data/app.db cannot be read: {exc}")
    finally:
        after.close()
    return problems
