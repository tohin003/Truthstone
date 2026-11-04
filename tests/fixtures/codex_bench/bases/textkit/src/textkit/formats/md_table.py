"""GitHub-flavoured Markdown tables, for READMEs and pull request descriptions."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if "|" in text:
        text = text.replace("|", "\\|")
    return text


def _line(cells: Iterable[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def render(rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    lines = [_line(_cell(header) for header in headers), "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend(_line(_cell(value) for value in row) for row in rows)
    return "\n".join(lines) + "\n"
