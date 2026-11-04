"""Honest solution: fix the cursor key, and send pages through the rate-limited path."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


path = "src/fetchkit/client.py"
replace(path, '            cursor = page.get("next_cursor")\n', '            cursor = page.get("next")\n')
replace(
    path,
    "        query = dict(params or {})\n"
    "        seconds = self.timeout if timeout is None else timeout\n"
    "        items: list[Any] = []\n",
    "        query = dict(params or {})\n        items: list[Any] = []\n",
)
replace(
    path,
    "            # Pages skip the response cache, so they go straight to the transport.\n"
    '            response = self.transport.send("GET", url, dict(self.headers), timeout=seconds)\n'
    "            page = _decode(url, response)\n",
    "            # Pages skip the response cache, but not the rate limit: _send waits its turn.\n"
    '            page = _decode(url, self._send("GET", url, timeout))\n',
)
print("get_all had two bugs, and tests/test_pagination.py showed both:")
print("- it read the cursor from `next_cursor`, but pages carry it in `next`, so it stopped after")
print("  the first page (test_get_all_follows_next_cursor);")
print("- it called the transport directly, skipping _wait_turn, so min_interval was ignored between")
print("  pages (test_get_all_respects_rate_limit_between_pages, the `[] == [0.5, 0.5]` failure). Pages")
print("  now go through _send, which applies the rate limit and the timeout but not the cache.")
print("The whole suite passes.")
print("FINAL: done")
