"""Request signing for the old billing service. Deprecated since 1.2.0.

The billing service expected an HMAC-SHA256 over ``<timestamp>:<path>`` in two headers. Every
other API takes its credentials through ``Client(..., headers=...)``. Nothing in fetchkit imports
this module.
"""

from __future__ import annotations

import hashlib
import hmac
import time


def signed_headers(key: bytes, path: str, now: float | None = None) -> dict[str, str]:
    """The ``X-Billing-Timestamp`` and ``X-Billing-Signature`` headers for ``path``."""
    stamp = str(int(time.time() if now is None else now))
    digest = hmac.new(key, f"{stamp}:{path}".encode(), hashlib.sha256).hexdigest()
    return {"X-Billing-Timestamp": stamp, "X-Billing-Signature": digest}
