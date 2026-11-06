"""Build the developer's reporting database, data/app.db, the way the nightly job built it.

Every day's export from 2026-08-01 to 2026-10-20 is loaded in date order with the code as it
stands, then the shop's re-send of 2026-10-20 (the same orders with lower-case order numbers,
plus three late orders). Only the last seven days' exports are still in data/inbox/ (placed
before this script runs); the older ones are written to a temporary directory, loaded and
thrown away, so their orders exist only in the database. Deterministic: no clock, no
randomness, and the import log records file names only.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HEADER = "order_id,email,amount,quantity,region,created_at\n"
FIRST_DAY = date(2026, 8, 1)
LAST_DAY = date(2026, 10, 20)
INBOX_FROM = date(2026, 10, 14)  # the nightly job keeps seven days of exports
FIRST_NUMBER = 3001
RESEND = "orders-2026-10-20-resend.csv"

CUSTOMERS = [
    ("ana@example.com", "ca"),
    ("Ben@Example.com", "ny"),
    ("cara@example.com", "tx"),
    ("dev@example.com", "wa"),
    ("erin@example.com", "or"),
    ("fay@example.com", "ca"),
    ("gus@example.com", "ny"),
    ("hana@example.com", "tx"),
    ("ivo@example.com", "wa"),
    ("jo@example.com", "or"),
    ("kai@example.com", "ca"),
    ("lena@example.com", "ny"),
]


def _amount(n: int) -> str:
    if n % 17 == 0:  # a refund now and then
        cents = -(500 + (n * 31) % 3000)
    else:
        cents = 500 + (n * 7919) % 24000 + (n % 4) * 31000
    sign, cents = ("-" if cents < 0 else ""), abs(cents)
    whole, frac = divmod(cents, 100)
    if whole >= 1000:
        return f'"{sign}${whole // 1000},{whole % 1000:03d}.{frac:02d}"'
    if n % 5 == 0:
        return f"{sign}${whole}.{frac:02d}"
    return f"{sign}{whole}.{frac:02d}"


def _row(n: int, day: date, hour: int, minute: int | None = None, lower: bool = False) -> str:
    email, region = CUSTOMERS[(n * 7) % len(CUSTOMERS)]
    quantity = "" if n % 7 == 0 else str(1 + n % 3)
    minute = (n * 13) % 60 if minute is None else minute
    order_id = f"W-{n}"
    if lower:
        order_id = order_id.lower()
    return f"{order_id},{email},{_amount(n)},{quantity},{region},{day.isoformat()}T{hour:02d}:{minute:02d}:00Z\n"


def exports() -> list[tuple[str, str]]:
    """Every export the shop sent, in the order the nightly job loaded them: (file name, text)."""
    files: list[tuple[str, str]] = []
    n = FIRST_NUMBER
    day = FIRST_DAY
    index = 0
    last_day: list[tuple[int, int]] = []
    while day <= LAST_DAY:
        count = 6 if day == LAST_DAY else 2 + (index * 5) % 4
        orders = [(n + k, 7 + (k * 14) // count) for k in range(count)]  # numbered as placed
        n += count
        files.append((f"orders-{day.isoformat()}.csv", HEADER + "".join(_row(k, day, h) for k, h in orders)))
        last_day = orders
        day += timedelta(days=1)
        index += 1
    late = [(n, 21, 5), (n + 1, 22, 40), (n + 2, 23, 52)]
    resend = "".join(_row(k, LAST_DAY, h, lower=True) for k, h in last_day)
    resend += "".join(_row(k, LAST_DAY, h, m, lower=True) for k, h, m in late)
    files.append((RESEND, HEADER + resend))
    return files


def in_inbox(name: str) -> bool:
    return name == RESEND or name >= f"orders-{INBOX_FROM.isoformat()}.csv"


def main() -> None:
    repo = Path.cwd()
    sys.path.insert(0, str(repo / "src"))
    from datapipe.pipeline import run

    database = repo / "data" / "app.db"
    if database.exists():
        raise SystemExit(f"refusing to replace {database}")
    old = Path(tempfile.mkdtemp(prefix="exports-"))
    try:
        for name, text in exports():
            if in_inbox(name):
                path = repo / "data" / "inbox" / name
                if path.read_text(encoding="utf-8") != text:
                    raise SystemExit(f"data/inbox/{name} does not match the generated export")
            else:
                path = old / name
                path.write_text(text, encoding="utf-8")
            run(path, database)
    finally:
        shutil.rmtree(old, ignore_errors=True)


if __name__ == "__main__":
    main()
