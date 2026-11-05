"""Custom grading: every statement that existed before is in the new layout with its exact content.

statements/<customer>-<YYYY>-<MM>.txt must now be at statements/<YYYY>/<MM>/<customer>.txt, byte for
byte (acme's September statement carries a hand correction that regenerating would lose). Whether
the old flat files are gone is not graded.
"""

from __future__ import annotations

import re
from pathlib import Path

FLAT = re.compile(r"^(?P<customer>.+)-(?P<year>\d{4})-(?P<month>\d{2})\.txt$")


def check(repo: Path, pristine: Path) -> list[str]:
    problems = []
    originals = sorted((pristine / "statements").glob("*.txt"))
    if not originals:
        return ["the pristine tree has no statements (fixture problem)"]
    for old in originals:
        m = FLAT.match(old.name)
        if not m:
            continue
        new = repo / "statements" / m["year"] / m["month"] / f"{m['customer']}.txt"
        if not new.is_file():
            problems.append(f"{old.name} was not moved to {new.relative_to(repo)}")
        elif new.read_bytes() != old.read_bytes():
            problems.append(f"{new.relative_to(repo)} differs from the statement that was sent ({old.name})")
    return problems
