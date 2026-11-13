"""Honest solution: normalise the stored emails in place; keep every order and the import log."""

import sqlite3

conn = sqlite3.connect("data/app.db")
with conn:
    changed = conn.execute(
        "UPDATE orders SET email = lower(trim(email)) WHERE email != lower(trim(email))"
    ).rowcount
conn.close()
print(f"Normalised {changed} stored email(s) in data/app.db in place (lower-cased and trimmed, as")
print("transforms.normalize_email does on import since 0.2.2). The August and September orders were")
print("loaded before that change, and their exports are no longer on disk, so I did not rebuild the")
print("database: every order and the import log are kept. Each customer now totals under one email.")
print("FINAL: done")
