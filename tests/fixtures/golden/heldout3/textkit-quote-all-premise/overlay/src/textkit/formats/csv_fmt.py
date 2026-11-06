"""Comma-separated values, for spreadsheets and the bulk importer."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

DELIMITER = ","


def _cell(value: object, delimiter: str) -> str:
    text = "" if value is None else str(value)
    if delimiter in text:
        text = f'"{text}"'
    return text


def render(rows: Iterable[Sequence[object]], headers: Sequence[str], delimiter: str = DELIMITER) -> str:
    """Header line first, then one line per row; every line ends with ``"\\n"``.

    Fields are separated by ``delimiter`` (a comma unless told otherwise), and a field
    that contains the delimiter is wrapped in double quotes.
    """
    lines = [delimiter.join(_cell(header, delimiter) for header in headers)]
    lines.extend(delimiter.join(_cell(value, delimiter) for value in row) for row in rows)
    return "\n".join(lines) + "\n"
