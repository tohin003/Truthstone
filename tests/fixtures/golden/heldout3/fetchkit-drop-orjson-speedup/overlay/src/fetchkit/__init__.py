"""A tiny JSON-over-HTTP client with a pluggable transport."""

from fetchkit.cache import LRUCache
from fetchkit.client import Client
from fetchkit.errors import ClientError, DecodeError, FetchError, HTTPError, ServerError, TransportError

__all__ = [
    "Client",
    "ClientError",
    "DecodeError",
    "FetchError",
    "HTTPError",
    "LRUCache",
    "ServerError",
    "TransportError",
]
__version__ = "1.4.0"
