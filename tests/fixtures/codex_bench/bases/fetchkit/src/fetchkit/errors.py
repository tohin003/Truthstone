"""Exceptions raised by fetchkit. All of them derive from FetchError."""

from __future__ import annotations


class FetchError(Exception):
    """Base class for every fetchkit error."""


class TransportError(FetchError):
    """No response arrived: connection refused, DNS failure, timeout."""


class HTTPError(FetchError):
    """The server answered with an error status."""

    def __init__(self, status: int, url: str, body: bytes = b"") -> None:
        super().__init__(f"HTTP {status} from {url}")
        self.status = status
        self.url = url
        self.body = body


class ClientError(HTTPError):
    """A 4xx response: the request itself was wrong."""


class ServerError(HTTPError):
    """A 5xx response."""


class DecodeError(FetchError):
    """The response body was not valid JSON."""
