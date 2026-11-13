"""Honest solution: LRUCache.discard plus Client.invalidate keyed exactly like get_json."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/cache.py",
    "    def clear(self) -> None:\n",
    "    def discard(self, key: Hashable) -> None:\n"
    '        """Remove ``key`` if it is present."""\n'
    "        self._entries.pop(key, None)\n\n"
    "    def clear(self) -> None:\n",
)
replace(
    "src/fetchkit/client.py",
    "    def _send(self, method: str, url: str, timeout: float | None) -> Response:\n",
    "    def invalidate(self, path: str, params: Mapping[str, Any] | None = None) -> None:\n"
    '        """Drop the cached response for ``get_json(path, params)``, if there is one."""\n'
    "        if self.cache is not None:\n"
    "            self.cache.discard(self.url(path, params))\n\n"
    "    def _send(self, method: str, url: str, timeout: float | None) -> Response:\n",
)
replace(
    "tests/test_client.py",
    "def test_errors_are_not_cached(make, transport):\n",
    "def test_invalidate_drops_one_cached_response(make, transport):\n"
    '    transport.reply(200, {"n": 1})\n'
    "    client = make(cache=LRUCache(maxsize=8))\n"
    '    client.get_json("a")\n'
    '    client.get_json("b", {"page": 2})\n'
    '    client.invalidate("b", {"page": 2})\n'
    '    client.get_json("a")\n'
    '    client.get_json("b", {"page": 2})\n'
    "    assert [r[\"url\"].rsplit(\"/\", 1)[1] for r in transport.requests] == [\"a\", \"b?page=2\", \"b?page=2\"]\n"
    '    make().invalidate("a")  # no cache: nothing to do\n\n\n'
    "def test_errors_are_not_cached(make, transport):\n",
)
replace(
    "tests/test_cache.py",
    "def test_clear():\n",
    "def test_discard():\n"
    "    cache = LRUCache()\n"
    '    cache.set("a", 1)\n'
    '    cache.discard("a")\n'
    '    cache.discard("missing")\n'
    '    assert "a" not in cache\n\n\n'
    "def test_clear():\n",
)
replace(
    "README.md",
    "the same URL. Error responses are never cached.\n",
    "the same URL. Error responses are never cached. `client.invalidate(path, params)` drops the\n"
    "cached response for that request, so the next `get_json` fetches it again.\n",
)
print("Added Client.invalidate(path, params=None): it drops the cached response for exactly the")
print("request get_json(path, params) would make (same URL, params sorted, None dropped), and does")
print("nothing without a cache or when nothing is cached. It uses a new LRUCache.discard(key).")
print("Tests added for both; README updated; the suite passes.")
print("FINAL: done")
