"""A YAML list of mappings, for fixtures and config snippets."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if ": " in text:
        text = f'"{text}"'
    return text


def render(rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    lines = []
    for row in rows:
        for position, (header, value) in enumerate(zip(headers, row)):
            lead = "- " if position == 0 else "  "
            lines.append(f"{lead}{_cell(header)}: {_cell(value)}")
    if not lines:
        return "[]\n"
    return "\n".join(lines) + "\n"
