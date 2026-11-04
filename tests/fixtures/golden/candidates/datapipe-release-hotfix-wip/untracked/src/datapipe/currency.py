"""Currency codes on export rows (work in progress: not stored in the database yet)."""

from __future__ import annotations

import re

DEFAULT_CURRENCY = "USD"
_CODE = re.compile(r"^[A-Z]{3}$")


def parse_currency(text: str) -> str:
    """A three-letter ISO 4217 code, upper-cased; a blank cell means USD."""
    if not text:
        return DEFAULT_CURRENCY
    code = text.upper()
    if not _CODE.match(code):
        raise ValueError("expected a three-letter currency code")
    return code
