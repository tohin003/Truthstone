"""The nightly export jobs: which formatter each consumer gets, and with which options.

Each entry names a module of ``textkit.formats`` and the keyword options its ``render`` is
called with (see ``textkit.formats.render_as``). The jobs runner calls ``export`` once per
consumer every night and uploads the result.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from textkit.formats import render_as

EXPORTS: dict[str, tuple[str, dict[str, Any]]] = {
    # The warehouse's bulk importer reads semicolon-separated files.
    "bulk-importer": ("csv_fmt", {"delimiter": ";"}),
    "analytics": ("tsv_fmt", {}),
    "developer-docs": ("md_table", {"align": "left"}),
    "web": ("html_table", {}),
    "public-api": ("json_fmt", {}),
    "partner-bridge": ("xml_fmt", {}),
}


def export(name: str, rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    """Render ``rows`` the way the consumer ``name`` takes them."""
    try:
        fmt, options = EXPORTS[name]
    except KeyError:
        raise ValueError(f"unknown export: {name!r}") from None
    return render_as(fmt, rows, headers, **options)
