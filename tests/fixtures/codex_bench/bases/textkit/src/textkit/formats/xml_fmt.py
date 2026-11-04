"""XML rows for the partner bridge. Column names are used as element names."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if "<" in text:
        text = text.replace("<", "&lt;")
    return text


def render(rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    lines = ["<rows>"]
    for row in rows:
        fields = "".join(f"<{header}>{_cell(value)}</{header}>" for header, value in zip(headers, row))
        lines.append(f"  <row>{fields}</row>")
    lines.append("</rows>")
    return "\n".join(lines) + "\n"
