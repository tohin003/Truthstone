"""A tiny JSON-over-HTTP client with a pluggable transport."""

from fetchkit.cache import LRUCache
from fetchkit.client import Client
from fetchkit.compat import fetch_url_json
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
    "fetch_url_json",
]
__version__ = "1.3.0"
