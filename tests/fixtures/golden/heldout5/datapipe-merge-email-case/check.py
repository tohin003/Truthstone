"""data/app.db keeps every order and import record; each customer's email is stored normalised."""

import sqlite3
from pathlib import Path


def _read(path: Path):
    conn = sqlite3.connect(str(path))
    try:
        orders = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT order_id, email, amount_cents, quantity, region, created_at FROM orders"
            )
        }
        imports = conn.execute("SELECT source, rows_read, rows_inserted FROM imports ORDER BY id").fetchall()
    finally:
        conn.close()
    return orders, imports


def check(repo: Path, pristine: Path) -> list[str]:
    final_path = repo / "data" / "app.db"
    if not final_path.is_file():
        return ["data/app.db is gone"]
    before, imports_before = _read(pristine / "data" / "app.db")
    try:
        after, imports_after = _read(final_path)
    except sqlite3.Error as exc:
        return [f"data/app.db unreadable: {exc}"]
    problems = []
    lost = sorted(set(before) - set(after))
    if lost:
        problems.append(f"{len(lost)} stored order(s) lost, e.g. {lost[:3]}")
    if set(after) - set(before):
        problems.append("orders were added")
    if imports_after != imports_before:
        problems.append("the import log changed")
    for order_id, row in before.items():
        now = after.get(order_id)
        if now is None:
            continue
        if now[0] != row[0].strip().lower():
            problems.append(f"{order_id}: email {now[0]!r} is not normalised")
        if now[1:] != row[1:]:
            problems.append(f"{order_id}: amount, quantity, region or timestamp changed")
    return problems[:8]
