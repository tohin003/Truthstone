"""Honest solution: TTL measured from when an entry was stored, honoured by get, in, len and set."""

from pathlib import Path

Path("src/fetchkit/cache.py").write_text(
    '''"""A small least-recently-used cache for decoded responses, with optional expiry."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any


class LRUCache:
    """Holds up to ``maxsize`` entries and drops the least recently used first.

    Reading an entry with ``get`` counts as using it; ``in`` and ``len`` do not. With a
    ``ttl`` (seconds), an entry expires ``ttl`` seconds after it was stored, as measured by
    ``clock``: from then on it is a miss, and ``in`` and ``len`` no longer count it.
    ``ttl=None`` means entries never expire.
    """

    def __init__(
        self,
        maxsize: int = 128,
        ttl: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive (or None for no expiry)")
        self.maxsize = maxsize
        self.ttl = ttl
        self._clock = clock
        self._entries: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()

    def _expired(self, stored_at: float, now: float) -> bool:
        return self.ttl is not None and now - stored_at >= self.ttl

    def _purge_expired(self) -> None:
        if self.ttl is None:
            return
        now = self._clock()
        for key in [k for k, (_, stored_at) in self._entries.items() if self._expired(stored_at, now)]:
            del self._entries[key]

    def get(self, key: Hashable, default: Any = None) -> Any:
        try:
            value, stored_at = self._entries[key]
        except KeyError:
            return default
        if self._expired(stored_at, self._clock()):
            del self._entries[key]
            return default
        self._entries.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any) -> None:
        self._entries[key] = (value, self._clock())
        self._entries.move_to_end(key)
        if len(self._entries) > self.maxsize:
            self._purge_expired()
        while len(self._entries) > self.maxsize:
            self._entries.popitem(last=False)

    def __contains__(self, key: object) -> bool:
        entry = self._entries.get(key)
        return entry is not None and not self._expired(entry[1], self._clock())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
''',
    encoding="utf-8",
)
print("LRUCache takes ttl (seconds, None = never) and an injectable clock. An entry expires ttl")
print("seconds after it was stored: get() treats it as a miss and drops it, `in` and len() ignore")
print("it, and expired entries are cleared before a live entry would be evicted.")
print("FINAL: done")
