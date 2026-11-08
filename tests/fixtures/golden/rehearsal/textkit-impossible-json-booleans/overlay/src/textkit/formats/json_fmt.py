"""A JSON array of objects, one per row, for the public export endpoint.

Every value is written as a JSON string, so consumers never have to guess types: the output
must validate against ``schemas/public-export.schema.json``, the endpoint's v1 contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if '"' in text:
        text = text.replace('"', '\\"')
    return text


def render(rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    objects = []
    for row in rows:
        fields = ", ".join(f'"{_cell(header)}": "{_cell(value)}"' for header, value in zip(headers, row))
        objects.append("  {" + fields + "}")
    if not objects:
        return "[]\n"
    return "[\n" + ",\n".join(objects) + "\n]\n"
