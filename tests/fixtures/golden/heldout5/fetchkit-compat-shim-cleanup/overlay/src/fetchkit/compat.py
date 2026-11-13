"""Deprecated: the pre-1.0 one-shot helper, kept for the old billing scripts.

``fetch_url_json(url)`` predates ``Client``. New code should build a ``Client`` and call
``get_json``; this shim only splits the URL and does that for you.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fetchkit.client import Client
from fetchkit.transport import DEFAULT_TIMEOUT, Transport


def fetch_url_json(
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    transport: Transport | None = None,
) -> Any:
    """GET an absolute ``url`` and return its decoded JSON. Deprecated since 1.2.0."""
    warnings.warn("fetch_url_json is deprecated; use Client.get_json", DeprecationWarning, stacklevel=2)
    parts = urlsplit(url)
    base = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
    path = parts.path.lstrip("/") + (f"?{parts.query}" if parts.query else "")
    client = Client(base, transport=transport, timeout=timeout, headers=headers)
    return client.get_json(path)
