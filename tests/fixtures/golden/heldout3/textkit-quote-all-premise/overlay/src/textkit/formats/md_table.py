"""GitHub-flavoured Markdown tables, for READMEs and pull request descriptions."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

# The separator row's cell for each alignment.
_RULES = {None: "---", "left": ":---", "right": "---:", "center": ":---:"}


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if "|" in text:
        text = text.replace("|", "\\|")
    return text


def _line(cells: Iterable[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def render(rows: Iterable[Sequence[object]], headers: Sequence[str], align: str | None = None) -> str:
    """A Markdown table. ``align`` ("left", "right" or "center") aligns every column."""
    try:
        rule = _RULES[align]
    except KeyError:
        raise ValueError(f"unknown alignment: {align!r}") from None
    lines = [_line(_cell(header) for header in headers), "|" + "|".join(rule for _ in headers) + "|"]
    lines.extend(_line(_cell(value) for value in row) for row in rows)
    return "\n".join(lines) + "\n"
