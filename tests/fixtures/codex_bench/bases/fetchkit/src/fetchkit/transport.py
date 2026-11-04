"""Transports: how a request reaches the network.

A transport sends one request and returns a ``Response``. Error statuses are ordinary
responses (deciding what a 404 means is the client's job); a transport raises
``TransportError`` only when no response arrives at all.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from fetchkit.errors import TransportError

#: Socket timeout, in seconds, for requests that do not carry their own. The service
#: health checks send through UrllibTransport directly and rely on this value.
DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def send(
        self, method: str, url: str, headers: dict[str, str], timeout: float | None = None
    ) -> Response:
        """Send one request. Raises TransportError if no response arrives."""
        ...


class UrllibTransport:
    """The default transport: ``urllib`` from the standard library."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def send(
        self, method: str, url: str, headers: dict[str, str], timeout: float | None = None
    ) -> Response:
        request = urllib.request.Request(url, method=method, headers=dict(headers))
        seconds = self.timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(request, timeout=seconds) as raw:
                return Response(raw.status, raw.read(), dict(raw.headers.items()))
        except urllib.error.HTTPError as exc:
            headers_out = dict(exc.headers.items()) if exc.headers is not None else {}
            return Response(exc.code, exc.read(), headers_out)
        except (urllib.error.URLError, OSError) as exc:
            raise TransportError(f"{method} {url}: {exc}") from exc
