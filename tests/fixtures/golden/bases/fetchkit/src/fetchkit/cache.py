"""A small least-recently-used cache for decoded responses."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable
from typing import Any


class LRUCache:
    """Holds up to ``maxsize`` entries and drops the least recently used first.

    Reading an entry with ``get`` counts as using it; ``in`` and ``len`` do not.
    """

    def __init__(self, maxsize: int = 128) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self.maxsize = maxsize
        self._entries: OrderedDict[Hashable, Any] = OrderedDict()

    def get(self, key: Hashable, default: Any = None) -> Any:
        try:
            value = self._entries[key]
        except KeyError:
            return default
        self._entries.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any) -> None:
        self._entries[key] = value
        self._entries.move_to_end(key)
        while len(self._entries) > self.maxsize:
            self._entries.popitem(last=False)

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
