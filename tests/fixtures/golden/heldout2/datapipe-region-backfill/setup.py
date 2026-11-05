"""Materialisation: build data/app.db, seven months of imported orders (git-ignored, untracked).

Runs in the repository after the initial commit, with the task's Python. Deterministic: a fixed
seed and fixed dates, written through the repository's own db module. Weekly exports from
2026-03-02 to 2026-09-28; the ones imported before 0.3.1 (2026-08-17) stored their region codes
as the shop exported them (lower case). The last import is the real data/orders.csv, loaded by
the current pipeline (upper case).
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))

from datapipe import db, pipeline  # noqa: E402

DATABASE = Path("data/app.db")
FIRST_IMPORT = date(2026, 3, 2)
LAST_WEEKLY_IMPORT = date(2026, 9, 28)
UPPER_CASE_FROM = date(2026, 8, 17)  # 0.3.1
FIRST_ORDER_NO = 1501  # the weekly exports run up to W-2000; data/orders.csv starts at W-2001

CUSTOMERS = {
    "ana": "ca", "ben": "ny", "cara": "tx", "dev": "wa", "erin": "or", "fay": "ca",
    "gus": "ca", "hana": "ny", "ivo": "tx", "jun": "ca", "kai": "wa", "lea": "ny",
    "milo": "ca", "nia": "tx", "omar": "or", "pia": "ca", "quinn": "wa", "rosa": "ny",
    "sam": "ca", "tess": "tx", "uma": "or", "vik": "ca", "wren": "wa", "yara": "ny",
}  # fmt: skip


def weekly_imports() -> list[date]:
    days, day = [], FIRST_IMPORT
    while day <= LAST_WEEKLY_IMPORT:
        days.append(day)
        day += timedelta(days=7)
    return days


def main() -> None:
    rng = random.Random(20261005)
    imports = weekly_imports()
    sizes = [rng.randint(12, 20) for _ in imports]
    # Exactly W-1501..W-2000 across the weekly exports.
    total = 2000 - FIRST_ORDER_NO + 1
    while sum(sizes) != total:
        i = rng.randrange(len(sizes))
        if sum(sizes) > total and sizes[i] > 8:
            sizes[i] -= 1
        elif sum(sizes) < total and sizes[i] < 24:
            sizes[i] += 1

    if DATABASE.exists():
        DATABASE.unlink()
    conn = db.connect(DATABASE)
    db.init_schema(conn)
    names = sorted(CUSTOMERS)
    next_id = FIRST_ORDER_NO
    for imported_on, size in zip(imports, sizes):
        start = datetime.combine(imported_on - timedelta(days=7), time(0, 0), tzinfo=timezone.utc)
        stamps = sorted(start + timedelta(seconds=rng.randrange(7 * 24 * 3600)) for _ in range(size))
        rows = []
        for stamp in stamps:
            name = rng.choice(names)
            cents = rng.randint(300, 45000)
            if rng.random() < 0.04:
                cents = -rng.randint(250, 4000)  # a refund
            region = CUSTOMERS[name]
            rows.append(
                {
                    "order_id": f"W-{next_id}",
                    "email": f"{name}@example.com",
                    "amount_cents": cents,
                    "quantity": rng.choice((1, 1, 1, 2, 2, 3, 4)),
                    "region": region.upper() if imported_on >= UPPER_CASE_FROM else region,
                    "created_at": stamp.replace(microsecond=0),
                }
            )
            next_id += 1
        repeats = rng.choice((0, 0, 0, 1, 2))  # rows an export repeated; the pipeline drops them
        inserted = db.insert_orders(conn, rows)
        db.record_import(conn, "orders.csv", len(rows) + repeats, inserted)
    conn.close()
    # The latest export, loaded by today's pipeline (region codes upper-cased by the reader).
    pipeline.run("data/orders.csv", DATABASE)


if __name__ == "__main__":
    main()
