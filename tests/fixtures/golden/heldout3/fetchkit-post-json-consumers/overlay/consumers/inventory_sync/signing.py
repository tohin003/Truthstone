"""Request signing for the stock service, which rejects unsigned requests.

Copied from inventory-sync (src/inventory_sync/signing.py).
"""

from __future__ import annotations

import hashlib
import hmac

from fetchkit.transport import Response, Transport, UrllibTransport


class SigningTransport:
    """Signs every request (HMAC-SHA256 of "METHOD URL") and sends it with ``inner``."""

    def __init__(self, secret: bytes, inner: Transport | None = None) -> None:
        self.secret = secret
        self.inner = inner if inner is not None else UrllibTransport()

    def send(self, method: str, url: str, headers: dict[str, str], timeout: float | None = None) -> Response:
        signature = hmac.new(self.secret, f"{method} {url}".encode(), hashlib.sha256).hexdigest()
        return self.inner.send(method, url, {**headers, "X-Signature": signature}, timeout=timeout)
