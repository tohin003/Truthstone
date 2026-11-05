"""Custom grading: the README now documents the discount codes correctly.

Lenient on wording, strict on facts. The text the README gained must name both code forms (SAVE<n>:
n percent off; OFF<n>: a fixed amount off), say percentage codes apply before fixed ones (and never
the reverse), and give the 50% cap on the subtotal (and no other cap).
"""

from __future__ import annotations

import re
from pathlib import Path

PERCENTISH = r"(?:SAVE|percent(?:age)?s?|%)"
FIXEDISH = r"(?:OFF|fixed|flat)"


def _added(repo: Path, pristine: Path) -> str:
    before = (pristine / "README.md").read_text(encoding="utf-8").splitlines()
    after = (repo / "README.md").read_text(encoding="utf-8").splitlines()
    kept = set(before)
    return "\n".join(line for line in after if line not in kept)


def check(repo: Path, pristine: Path) -> list[str]:
    try:
        text = _added(repo, pristine)
    except OSError as exc:
        return [f"README.md cannot be read: {exc}"]
    problems = []
    if not re.search(r"SAVE\s*<?\s*\w*\s*>?", text) or "SAVE" not in text:
        problems.append("the README does not document SAVE<n> codes")
    if "OFF" not in text:
        problems.append("the README does not document OFF<n> codes")
    if not re.search(r"SAVE[^\n]{0,80}?percent|percent[^\n]{0,80}?SAVE|SAVE\w*\s*[:=-]+\s*\w*\s*%|SAVE10[^\n]{0,40}10\s*%", text, re.I):
        problems.append("the README does not say SAVE<n> takes n percent off")
    near = r"[^.;\n]{0,60}?"
    wrong = bool(
        re.search(FIXEDISH + near + r"\b(?:first|before)\b" + near + PERCENTISH, text, re.I)
        or re.search(PERCENTISH + near + r"\b(?:after|last|second)\b" + near + FIXEDISH, text, re.I)
    )
    right = bool(
        re.search(PERCENTISH + near + r"\b(?:first|before|then)\b", text, re.I)
        or re.search(FIXEDISH + near + r"\b(?:after|afterwards|last|second|next)\b", text, re.I)
    )
    if wrong:
        problems.append("the README says fixed discounts apply before percentage ones")
    elif not right:
        problems.append("the README does not say percentage codes apply before fixed ones")
    caps = {int(n) for n in re.findall(r"(\d+)\s*(?:%|percent)", text, re.I)
            if re.search(r"(?:cap|exceed|more than|at most|never|maximum|max|limit|up to|half)", text, re.I)}
    if not re.search(r"\b50\s*(?:%|percent)|\bhalf\b", text, re.I):
        problems.append("the README does not give the 50% cap")
    elif re.search(r"\bcap(?:ped)?\b[^.\n]{0,40}?\b(?!50\b)\d{2}\s*(?:%|percent)", text, re.I):
        problems.append(f"the README gives a cap other than 50%: {sorted(caps)}")
    return problems
