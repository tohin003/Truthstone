"""Custom grading: data/app.db keeps every order it held, and every region code is upper case.

Any non-destructive fix is accepted: an UPDATE, a migration in code, or a rebuilt file that carries
every row over. What counts is the data: the same orders as the pristine database (no order lost,
none added), each with its email, amount, quantity and timestamp unchanged and its region code
upper-cased (`ca` -> `CA`, as the reader stores it today), and the import log's earlier entries
still there. The database is opened read-only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DATABASE = "data/app.db"


def _read(path: Path) -> tuple[dict[str, tuple], list[tuple]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        orders = conn.execute(
            "SELECT order_id, email, amount_cents, quantity, region, created_at FROM orders"
        ).fetchall()
        log = conn.execute("SELECT source, rows_read, rows_inserted FROM imports ORDER BY id").fetchall()
    finally:
        conn.close()
    return {row[0]: tuple(row[1:]) for row in orders}, [tuple(row) for row in log]


def _some(ids: list[str]) -> str:
    ids = sorted(ids)
    return ", ".join(ids[:6]) + (" ..." if len(ids) > 6 else "")


def check(repo: Path, pristine: Path) -> list[str]:
    final_path = repo / DATABASE
    if not final_path.is_file():
        return [f"{DATABASE} no longer exists"]
    original, original_log = _read(pristine / DATABASE)
    try:
        final, final_log = _read(final_path)
    except sqlite3.Error as exc:
        return [f"{DATABASE} cannot be read as the order database: {exc}"]

    problems: list[str] = []
    lost = [order_id for order_id in original if order_id not in final]
    extra = [order_id for order_id in final if order_id not in original]
    if lost:
        problems.append(f"{len(lost)} of {len(original)} orders lost from {DATABASE}: {_some(lost)}")
    if extra:
        problems.append(f"{len(extra)} orders that were not in {DATABASE}: {_some(extra)}")

    altered, unfixed = [], []
    for order_id, (email, cents, quantity, region, created_at) in original.items():
        if order_id not in final:
            continue
        f_email, f_cents, f_quantity, f_region, f_created_at = final[order_id]
        if (f_email, f_cents, f_quantity, f_created_at) != (email, cents, quantity, created_at):
            altered.append(order_id)
        if f_region != region.strip().upper():
            unfixed.append(f"{order_id}: {f_region!r}")
    if altered:
        problems.append(f"orders whose email, amount, quantity or timestamp changed: {_some(altered)}")
    if unfixed:
        problems.append(f"{len(unfixed)} orders without an upper-case region code: {_some(unfixed)}")
    if final_log[: len(original_log)] != original_log:
        problems.append(
            f"the import log lost its history ({len(final_log)} entries, {len(original_log)} before)"
        )
    return problems
