"""The JSON client.

``Client`` joins paths onto a base URL, sends GET requests through a transport and
decodes the JSON that comes back. Error statuses raise: 4xx as ``ClientError``, 5xx as
``ServerError``. Decoded responses can be cached, and ``min_interval`` spaces requests out
for APIs with rate limits.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from fetchkit._speedups import encode_query
from fetchkit.cache import LRUCache
from fetchkit.errors import ClientError, DecodeError, ServerError
from fetchkit.transport import DEFAULT_TIMEOUT, Response, Transport, UrllibTransport

_MISSING = object()


class Client:
    def __init__(
        self,
        base_url: str,
        transport: Transport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Mapping[str, str] | None = None,
        cache: LRUCache | None = None,
        min_interval: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if "://" not in base_url:
            raise ValueError(f"base_url must be an absolute URL, got {base_url!r}")
        self.base_url = base_url.rstrip("/") + "/"
        self.transport = transport if transport is not None else UrllibTransport()
        self.timeout = timeout
        self.headers = {"Accept": "application/json", **(headers or {})}
        self.cache = cache
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last_sent: float | None = None

    def url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        """The base URL joined with ``path``, plus a sorted query string.

        ``None`` parameters are left out. ``path`` must be relative: an absolute URL would
        quietly send this client's headers to another host.
        """
        if "://" in path:
            raise ValueError(f"expected a path relative to {self.base_url}, got {path!r}")
        url = self.base_url + path.lstrip("/")
        query = encode_query(params or {})  # native/ when it is built, else fetchkit._query
        return f"{url}?{query}" if query else url

    def get_json(
        self, path: str, params: Mapping[str, Any] | None = None, timeout: float | None = None
    ) -> Any:
        """GET ``path`` and return the decoded JSON body (``None`` for an empty body)."""
        url = self.url(path, params)
        if self.cache is not None:
            cached = self.cache.get(url, _MISSING)
            if cached is not _MISSING:
                return cached
        data = _decode(url, self._send("GET", url, timeout))
        if self.cache is not None:
            self.cache.set(url, data)
        return data

    def _send(self, method: str, url: str, timeout: float | None) -> Response:
        self._wait_turn()
        seconds = self.timeout if timeout is None else timeout
        return self.transport.send(method, url, dict(self.headers), timeout=seconds)

    def _wait_turn(self) -> None:
        """Sleep until ``min_interval`` has passed since the previous request."""
        if self.min_interval > 0 and self._last_sent is not None:
            remaining = self.min_interval - (self._clock() - self._last_sent)
            if remaining > 0:
                self._sleep(remaining)
        self._last_sent = self._clock()


def _decode(url: str, response: Response) -> Any:
    if 400 <= response.status < 500:
        raise ClientError(response.status, url, response.body)
    if response.status >= 500:
        raise ServerError(response.status, url, response.body)
    if not response.body:
        return None
    try:
        return json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecodeError(f"{url}: response is not valid JSON ({exc})") from exc
