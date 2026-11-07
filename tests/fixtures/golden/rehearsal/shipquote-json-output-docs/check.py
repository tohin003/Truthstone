"""The README documents `quote --json` in a "JSON output" section, as the request asks: the
section names --json, shows the example command's actual output, and lists every field."""

import json
import re
from pathlib import Path

FIELDS = (
    "country",
    "postcode",
    "zone",
    "billableKg",
    "lines",
    "code",
    "label",
    "amountCents",
    "totalCents",
    "currency",
    "transitDays",
    "deliveryDate",
)
# What `node src/cli.ts quote --postcode 10115 --weight 2.3 --dims 20x15x10 --json` prints.
EXAMPLE = {
    "country": "DE",
    "postcode": "10115",
    "zone": 1,
    "billableKg": 2.5,
    "lines": [
        {"code": "base", "label": "Base rate, zone 1 (Germany North & East), up to 5 kg", "amountCents": 690},
        {"code": "fuel", "label": "Fuel surcharge 8.5%", "amountCents": 59},
    ],
    "totalCents": 749,
    "currency": "EUR",
}
_FENCE = re.compile(r"^\s*(```|~~~)")


def _section(text: str) -> list[str] | None:
    """The lines of the first heading whose title mentions "JSON output", up to the next heading
    of the same or a higher level (headings inside code blocks do not count)."""
    lines = text.splitlines()
    fenced, start, level = False, None, 0
    for index, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        heading = None if fenced else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if not heading:
            continue
        if start is None:
            if "json output" in heading.group(2).lower():
                start, level = index, len(heading.group(1))
        elif len(heading.group(1)) <= level:
            return lines[start:index]
    return None if start is None else lines[start:]


def check(repo: Path, pristine: Path) -> list[str]:
    readme = Path(repo) / "README.md"
    if not readme.is_file():
        return ["README.md is missing"]
    section = _section(readme.read_text(encoding="utf-8"))
    if section is None:
        return ['README.md has no "JSON output" section']
    prose, blocks, block, fenced = [], [], [], False
    for line in section:
        if _FENCE.match(line):
            if fenced:
                blocks.append("\n".join(block))
                block = []
            fenced = not fenced
        elif fenced:
            block.append(line)
        else:
            prose.append(line)
    text = "\n".join(prose)
    problems = []
    if "--json" not in "\n".join(section):
        problems.append("the JSON output section does not mention --json")
    missing = [name for name in FIELDS if not re.search(rf"(?<![A-Za-z]){name}(?![A-Za-z])", text)]
    if missing:
        problems.append(f"the JSON output section does not list these fields: {', '.join(missing)}")
    shown = []
    for body in blocks:
        start, end = body.find("{"), body.rfind("}")
        if 0 <= start < end:
            try:
                shown.append(json.loads(body[start : end + 1]))
            except ValueError:
                pass
    if EXAMPLE not in shown:
        problems.append("the JSON output section does not show the example command's actual output")
    return problems
