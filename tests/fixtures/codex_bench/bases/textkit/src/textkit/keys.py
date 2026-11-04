"""Rename the keys of records between naming styles.

Used by the export jobs, whose upstream payloads mix ``camelCase`` and ``snake_case``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from textkit.legacy_case import camelize, underscore

STYLES: dict[str, Callable[[str], str]] = {
    "snake": underscore,
    "camel": lambda key: camelize(underscore(key), upper_first=False),
    "pascal": lambda key: camelize(underscore(key)),
}


def rename_keys(record: Mapping[str, Any], style: str = "snake") -> dict[str, Any]:
    """A copy of ``record`` with every key in ``style``: ``snake``, ``camel`` or ``pascal``.

    Nested mappings are renamed too, including mappings inside lists.
    """
    try:
        convert = STYLES[style]
    except KeyError:
        raise ValueError(f"unknown key style: {style!r}") from None
    return _rename(record, convert)


def _rename(value: Any, convert: Callable[[str], str]) -> Any:
    if isinstance(value, Mapping):
        return {convert(str(key)): _rename(item, convert) for key, item in value.items()}
    if isinstance(value, list):
        return [_rename(item, convert) for item in value]
    return value
