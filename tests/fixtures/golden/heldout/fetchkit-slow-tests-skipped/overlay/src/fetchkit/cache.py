"""A small least-recently-used cache for decoded responses, bounded by count and by bytes."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable
from typing import Any


class LRUCache:
    """Holds up to ``maxsize`` entries and drops the least recently used first.

    Each entry has a ``size`` in bytes (the client passes the length of the response body).
    ``total_bytes`` is the sum over the entries currently held. With ``max_bytes`` set, the
    cache never holds more than that: storing an entry evicts least recently used entries
    until the total fits, so an entry larger than ``max_bytes`` on its own is not kept.

    Reading an entry with ``get`` counts as using it; ``in`` and ``len`` do not.
    """

    def __init__(self, maxsize: int = 128, max_bytes: int | None = None) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        if max_bytes is not None and max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        self.maxsize = maxsize
        self.max_bytes = max_bytes
        self.total_bytes = 0
        self._entries: OrderedDict[Hashable, tuple[Any, int]] = OrderedDict()

    def get(self, key: Hashable, default: Any = None) -> Any:
        try:
            value, _ = self._entries[key]
        except KeyError:
            return default
        self._entries.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any, size: int = 0) -> None:
        if size < 0:
            raise ValueError("size cannot be negative")
        if key in self._entries:
            # Already cached: refresh the value and its position. It is already counted.
            self._entries[key] = (value, size)
            self._entries.move_to_end(key)
            return
        self._entries[key] = (value, size)
        self.total_bytes += size
        self._evict()

    def _evict(self) -> None:
        while len(self._entries) > self.maxsize or (
            self.max_bytes is not None and self.total_bytes > self.max_bytes
        ):
            _, (_, size) = self._entries.popitem(last=False)
            self.total_bytes -= size

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self.total_bytes = 0
