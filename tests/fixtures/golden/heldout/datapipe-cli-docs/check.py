"""Custom grading: README.md gains a "Command line" section that gets the CLI's facts right.

The facts come from src/datapipe/__main__.py and pipeline.py: ``python -m datapipe EXPORT.csv
DATABASE.db`` loads a CSV export into a SQLite database and prints a summary. The exit status is
0 on success, 2 for a usage error (not exactly two arguments) and 1 when the export cannot be
read or cleaned. Wording and layout are free (prose, list or table). An exit status counts as
described when a word for its meaning sits in the same sentence as the number: anywhere in the
sentence when it names one status, otherwise between that number and its neighbours.
"""

from __future__ import annotations

import re
from pathlib import Path

README = "README.md"
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t#]*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
SECTION_TITLE = re.compile(r"\bcommand[- ]line\b", re.IGNORECASE)
ITEM = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")
SENTENCE_END = re.compile(r"(?<=[.;!?])\s+")
STATUS = re.compile(r"(?<![\w.$/-])([012])(?![\w%/]|[.,]\d)")
MEANING = {
    "2": re.compile(
        r"usage|argument|\bargs?\b|invocation|invoked|wrong number|command[- ]line|missing|"
        r"too (?:many|few)|exactly two|not two|two (?:paths|files|parameters|operands)",
        re.IGNORECASE,
    ),
    "1": re.compile(
        r"read|error|fail|invalid|\bbad\b|missing|cannot|can't|could ?n[o']t|not found|malformed|"
        r"problem|unreadable|reject|clean|pars|exception|no such|wrong",
        re.IGNORECASE,
    ),
}


def _section(text: str) -> list[str] | None:
    """The lines under the first heading that mentions "command line", up to the next peer heading."""
    lines = text.splitlines()
    fenced = False
    start = level = None
    for number, line in enumerate(lines):
        if FENCE.match(line):
            fenced = not fenced
            continue
        heading = None if fenced else HEADING.match(line)
        if heading is None:
            continue
        depth = len(heading.group(1))
        if start is None:
            if SECTION_TITLE.search(heading.group(2)):
                start, level = number, depth
        elif depth <= level:
            return lines[start + 1 : number]
    return None if start is None else lines[start + 1 :]


def _units(lines: list[str]) -> list[str]:
    """Paragraphs, with every list item and table row on its own."""
    units: list[str] = []
    current: list[str] = []
    for line in [*lines, ""]:
        if not line.strip() or FENCE.match(line):
            if current:
                units.append(" ".join(current))
                current = []
            continue
        if ITEM.match(line) and current:
            units.append(" ".join(current))
            current = []
        current.append(line.strip())
    return units


def _statuses(units: list[str]) -> dict[str, bool]:
    found = {"0": False, "1": False, "2": False}
    for unit in units:
        for sentence in SENTENCE_END.split(unit):
            hits = list(STATUS.finditer(sentence))
            for index, hit in enumerate(hits):
                code = hit.group(1)
                if code == "0":
                    found[code] = True
                    continue
                if len(hits) == 1:
                    near = [sentence]
                else:
                    start = hits[index - 1].end() if index else 0
                    end = hits[index + 1].start() if index + 1 < len(hits) else len(sentence)
                    near = [sentence[start : hit.start()], sentence[hit.end() : end]]
                if any(MEANING[code].search(text) for text in near):
                    found[code] = True
    return found


def check(repo: Path, pristine: Path) -> list[str]:
    path = repo / README
    if not path.is_file():
        return [f"{README} is missing"]
    text = path.read_text(encoding="utf-8")
    problems = []
    headings = [m.group(2) for m in map(HEADING.match, text.splitlines()) if m]
    for kept in ("Export format", "Scripts"):
        if not any(kept.lower() in heading.lower() for heading in headings):
            problems.append(f'{README} lost its "{kept}" section')
    lines = _section(text)
    if lines is None:
        return problems + [f'{README} has no "Command line" section']
    body = "\n".join(lines)
    lowered = body.lower()
    if not re.search(r"python3?\s+-m\s+datapipe", body):
        problems.append("the Command line section does not show `python -m datapipe`")
    if "csv" not in lowered or not any(word in lowered for word in ("database", ".db", "sqlite")):
        problems.append("the Command line section does not describe both arguments (CSV export, database)")
    if not re.search(r"\b(load|import|insert)", body, re.IGNORECASE):
        problems.append("the Command line section does not say what the command does")
    if not re.search(r"-m\s+datapipe\s+\S+\s+\S+", body):
        problems.append("the Command line section has no example invocation")
    found = _statuses(_units(lines))
    if not found["0"]:
        problems.append("exit status 0 (success) is not documented")
    if not found["2"]:
        problems.append("exit status 2 is not documented as a usage error (not exactly two arguments)")
    if not found["1"]:
        problems.append("exit status 1 is not documented as the status for an export that cannot be read")
    return problems
