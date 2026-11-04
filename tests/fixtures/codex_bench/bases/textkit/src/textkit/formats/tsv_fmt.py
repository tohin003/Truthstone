"""Tab-separated values, for pasting into spreadsheets."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

DELIMITER = "\t"


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if DELIMITER in text:
        text = text.replace(DELIMITER, " ")
    return text


def render(rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    """Header line first, then one line per row; every line ends with ``"\\n"``."""
    lines = [DELIMITER.join(_cell(header) for header in headers)]
    lines.extend(DELIMITER.join(_cell(value) for value in row) for row in rows)
    return "\n".join(lines) + "\n"
