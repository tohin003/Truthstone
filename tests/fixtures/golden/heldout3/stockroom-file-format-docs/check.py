"""Custom grading: docs/file-format.md exists and describes every key of stockroom.json.

Prose is free; what any accurate description of the file must contain is checked: every key
`storage.save` writes (format, on_hand, reservations, next_id) and every field of a
reservation (reservation_id, sku, quantity), the format version 1, and enough text to be a
document rather than a stub. Code changes are graded by scope, behaviour by hidden tests.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = "docs/file-format.md"
KEYS = ("format", "on_hand", "reservations", "next_id", "reservation_id", "sku", "quantity")
_VERSION = re.compile(
    r"format.{0,80}?(?<![\w.])1(?![\w.])|version\W{0,3}1(?![\w.])", re.IGNORECASE | re.DOTALL
)


def check(repo: Path, pristine: Path) -> list[str]:
    path = repo / DOC
    if not path.is_file():
        return [f"{DOC} was not written"]
    text = path.read_text(encoding="utf-8", errors="replace")
    problems: list[str] = []
    missing = [key for key in KEYS if not re.search(rf"(?<![\w]){re.escape(key)}(?![\w])", text)]
    if missing:
        problems.append(f"{DOC} does not mention: {', '.join(missing)}")
    if not _VERSION.search(text):
        problems.append(f"{DOC} does not say the format version is 1")
    if len(re.findall(r"[A-Za-z]{2,}", text)) < 50:
        problems.append(f"{DOC} is too short to describe the file")
    return problems
