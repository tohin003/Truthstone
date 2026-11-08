"""isostamp 1.2.0: strict ISO-8601 timestamps.

    >>> parse_utc("2026-10-03T09:15:00Z")
    datetime.datetime(2026, 10, 3, 9, 15, tzinfo=datetime.timezone.utc)

Only the UTC designator ``Z`` is accepted as a zone. Numeric offsets (``+01:00``) are not
supported yet (upstream issue #31).

Copyright (c) 2023-2026 the isostamp authors. MIT License.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

__version__ = "1.2.0"

# TODO(#31): accept numeric offsets such as +01:00 and convert them to UTC.
_STAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z")


def parse_utc(text: str) -> datetime:
    """``YYYY-MM-DDTHH:MM:SSZ`` as an aware UTC datetime. Raises ValueError on anything else."""
    match = _STAMP.fullmatch(text)
    if not match:
        raise ValueError(f"not an ISO-8601 UTC timestamp: {text!r}")
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def format_utc(moment: datetime) -> str:
    """The inverse of ``parse_utc`` for an aware datetime."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
