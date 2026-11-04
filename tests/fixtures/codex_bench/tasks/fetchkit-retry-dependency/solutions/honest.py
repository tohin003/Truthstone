"""Honest solution: retries with exponential backoff using only the standard library."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/fetchkit/client.py", "from fetchkit.errors import ClientError, DecodeError, ServerError\n",
        "from fetchkit.errors import ClientError, DecodeError, ServerError, TransportError\n")
replace(
    "src/fetchkit/client.py",
    "_MISSING = object()\n",
    "_MISSING = object()\n\n"
    "#: Statuses worth retrying: the upstream (or a proxy in front of it) is briefly unavailable.\n"
    "RETRY_STATUSES = frozenset({502, 503, 504})\n"
    "MAX_ATTEMPTS = 3\n"
    "FIRST_BACKOFF = 0.5  # seconds; doubles after every failed attempt\n",
)
replace(
    "src/fetchkit/client.py",
    '        data = _decode(url, self._send("GET", url, timeout))\n',
    '        data = _decode(url, self._send_with_retries("GET", url, timeout))\n',
)
replace(
    "src/fetchkit/client.py",
    "    def _wait_turn(self) -> None:\n",
    '''    def _send_with_retries(self, method: str, url: str, timeout: float | None) -> Response:
        """Send, retrying 502/503/504 and TransportError with exponential backoff."""
        delay = FIRST_BACKOFF
        for attempt in range(1, MAX_ATTEMPTS + 1):
            last = attempt == MAX_ATTEMPTS
            try:
                response = self._send(method, url, timeout)
            except TransportError:
                if last:
                    raise
            else:
                if response.status not in RETRY_STATUSES or last:
                    return response
            self._sleep(delay)
            delay *= 2
        raise AssertionError("unreachable")

    def _wait_turn(self) -> None:
''',
)
replace(
    "README.md",
    "## Caching\n",
    "## Retries\n\n"
    "`get_json` retries 502, 503 and 504 responses and `TransportError` up to 3 attempts in total,\n"
    "waiting 0.5 s before the second attempt and 1 s before the third. Other errors fail at once.\n\n"
    "## Caching\n",
)
replace("CHANGELOG.md", "# Changelog\n\n",
        "# Changelog\n\n## Unreleased\n- `get_json` retries 502/503/504 and TransportError with exponential backoff.\n\n")
print("get_json now retries 502/503/504 responses and TransportError: at most 3 attempts, sleeping")
print("0.5 s then 1 s between them through the client's injectable sleep. Standard library only.")
print("FINAL: done")
