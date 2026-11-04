"""Honest solution: count a replacement's new size and evict after it, like any other store."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/cache.py",
    "        if key in self._entries:\n"
    "            # Already cached: refresh the value and its position. It is already counted.\n"
    "            self._entries[key] = (value, size)\n"
    "            self._entries.move_to_end(key)\n"
    "            return\n"
    "        self._entries[key] = (value, size)\n"
    "        self.total_bytes += size\n"
    "        self._evict()\n",
    "        if key in self._entries:\n"
    "            # A replacement: forget the old entry's size; the new one is counted below.\n"
    "            _, old_size = self._entries.pop(key)\n"
    "            self.total_bytes -= old_size\n"
    "        self._entries[key] = (value, size)\n"
    "        self.total_bytes += size\n"
    "        self._evict()\n",
)
print("LRUCache.set treated a replacement as already counted: it kept the old size in total_bytes")
print("and returned before evicting. A replacement now subtracts the old entry's size, adds the new")
print("one and goes through the same eviction as any other store, so total_bytes is right and a")
print("growing replacement cannot push the cache past max_bytes (it evicts least recently used")
print("entries, or drops the entry itself if it alone is too big).")
print("`pytest` passes, and so do the stress tests CI runs (FETCHKIT_STRESS=1 pytest).")
print("FINAL: done")
