"""The audit trail of every request catalog-export makes (copied from catalog-export,
src/catalog_export/audit.py)."""

from __future__ import annotations

from fetchkit.transport import Response, Transport, UrllibTransport


class AuditedTransport:
    """Sends with ``inner`` and appends "METHOD URL -> STATUS" to ``log`` for every request."""

    def __init__(self, log: list[str], inner: Transport | None = None) -> None:
        self.log = log
        self.inner = inner if inner is not None else UrllibTransport()

    def send(self, method: str, url: str, headers: dict[str, str], timeout: float | None = None) -> Response:
        response = self.inner.send(method, url, headers, timeout=timeout)
        self.log.append(f"{method} {url} -> {response.status}")
        return response
