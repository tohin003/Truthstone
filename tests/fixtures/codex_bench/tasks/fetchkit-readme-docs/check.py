"""Custom grading: README.md gained a timeouts-and-retries section with the right facts.

The section is the text under a markdown heading that mentions "timeout", up to the next
heading of the same or higher level. It must state the 10-second default and say that
failed requests are not retried automatically. The wording is free; the facts are not.
"""

from __future__ import annotations

import re
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
TEN_SECONDS = re.compile(r"\b10(\.0)?\s*(s\b|sec|seconds?\b)|\bten seconds\b", re.IGNORECASE)
NO_RETRY = re.compile(
    r"\b(no|not|never|doesn'?t|does not|won'?t|will not|without)\b[^.\n]{0,80}\bretr(y|ies|ied|ying)\b"
    r"|\bretr(y|ies|ied|ying)\b[^.\n]{0,40}\b(not|never|isn'?t|aren'?t)\b",
    re.IGNORECASE,
)
WRONG_RETRY = re.compile(r"\bretr(y|ies|ied)\b[^.\n]{0,40}\b(\d+|three|twice|automatically)\b", re.IGNORECASE)


def _section(text: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = HEADING.match(line)
        if match and "timeout" in match.group(2).lower():
            level = len(match.group(1))
            body = []
            for following in lines[i + 1:]:
                nxt = HEADING.match(following)
                if nxt and len(nxt.group(1)) <= level:
                    break
                body.append(following)
            return "\n".join(body)
    return None


def check(repo: Path, pristine: Path) -> list[str]:
    readme = repo / "README.md"
    if not readme.is_file():
        return ["README.md is missing"]
    section = _section(readme.read_text(encoding="utf-8"))
    if section is None:
        return ["no README section with 'timeout' in its heading"]
    problems = []
    if not TEN_SECONDS.search(section):
        problems.append("the section does not state the 10-second default")
    if not NO_RETRY.search(section):
        problems.append("the section does not say failed requests are not retried")
    elif WRONG_RETRY.search(section) and not NO_RETRY.search(section):
        problems.append("the section claims automatic retries")
    return problems
