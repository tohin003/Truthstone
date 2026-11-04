"""HTML tables for the docs site."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if "<" in text:
        text = text.replace("<", "&lt;")
    return text


def render(rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    head = "".join(f"<th>{_cell(header)}</th>" for header in headers)
    body = ["<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in row) + "</tr>" for row in rows]
    lines = ["<table>", f"<thead><tr>{head}</tr></thead>", "<tbody>", *body, "</tbody>", "</table>"]
    return "\n".join(lines) + "\n"
