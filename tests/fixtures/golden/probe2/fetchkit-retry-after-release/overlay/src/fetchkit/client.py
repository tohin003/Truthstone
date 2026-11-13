"""The JSON client.

``Client`` joins paths onto a base URL, sends GET requests through a transport and
decodes the JSON that comes back. Error statuses raise: 4xx as ``ClientError``, 5xx as
``ServerError``. Decoded responses can be cached, ``min_interval`` spaces requests out
for APIs with rate limits, and ``max_retries`` retries 429 and 503 responses, honouring
their ``Retry-After`` header (see the README's "Retries" section for the rules).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode

from fetchkit.cache import LRUCache
from fetchkit.errors import ClientError, DecodeError, ServerError
from fetchkit.transport import DEFAULT_TIMEOUT, Response, Transport, UrllibTransport

_MISSING = object()

#: Statuses that mean "try again later": Too Many Requests and Service Unavailable.
RETRY_STATUSES = (429, 503)


class Client:
    def __init__(
        self,
        base_url: str,
        transport: Transport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Mapping[str, str] | None = None,
        cache: LRUCache | None = None,
        min_interval: float = 0.0,
        max_retries: int = 0,
        retry_wait: float = 1.0,
        max_retry_wait: float = 60.0,
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
        self.max_retries = max_retries
        self.retry_wait = retry_wait
        self.max_retry_wait = max_retry_wait
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
        query = sorted((key, value) for key, value in (params or {}).items() if value is not None)
        return f"{url}?{urlencode(query)}" if query else url

    def get_json(
        self, path: str, params: Mapping[str, Any] | None = None, timeout: float | None = None
    ) -> Any:
        """GET ``path`` and return the decoded JSON body (``None`` for an empty body)."""
        url = self.url(path, params)
        if self.cache is not None:
            cached = self.cache.get(url, _MISSING)
            if cached is not _MISSING:
                return cached
        data = _decode(url, self._send_with_retries("GET", url, timeout))
        if self.cache is not None:
            self.cache.set(url, data)
        return data

    def _send(self, method: str, url: str, timeout: float | None) -> Response:
        self._wait_turn()
        seconds = self.timeout if timeout is None else timeout
        return self.transport.send(method, url, dict(self.headers), timeout=seconds)

    def _send_with_retries(self, method: str, url: str, timeout: float | None) -> Response:
        """Send, retrying 429 and 503 up to ``max_retries`` times."""
        attempt = 0
        while True:
            response = self._send(method, url, timeout)
            if response.status not in RETRY_STATUSES or attempt >= self.max_retries:
                return response
            attempt += 1
            self._sleep(self._retry_delay(response))

    def _retry_delay(self, response: Response) -> float:
        """Seconds to wait before retrying ``response``, from its Retry-After header."""
        value = response.headers.get("Retry-After")
        if value is None:
            return self.retry_wait
        try:
            seconds = float(value)
        except ValueError:
            return self.retry_wait
        return min(max(seconds, 0.0), self.max_retry_wait)

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
