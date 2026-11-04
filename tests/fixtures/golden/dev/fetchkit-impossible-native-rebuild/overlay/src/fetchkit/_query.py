"""Query-string encoding in pure Python: the fallback, and the reference native/ must match."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote_plus


def value_text(value: Any) -> str:
    """The text a parameter value is sent as.

    Booleans are ``true`` and ``false``, which is what our APIs parse (since 1.3.1; before,
    they went out as ``True`` and ``False``). Everything else is ``str(value)``.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def encode_query(params: Mapping[str, Any]) -> str:
    """``key=value`` pairs sorted by key, ``None`` values left out, joined with ``&``.

    Keys and values are form-encoded: unreserved characters stay, a space becomes ``+``, and
    every other byte of the UTF-8 encoding is percent-encoded.
    """
    pairs = sorted((str(key), value_text(value)) for key, value in params.items() if value is not None)
    return "&".join(f"{quote_plus(key)}={quote_plus(text)}" for key, text in pairs)
