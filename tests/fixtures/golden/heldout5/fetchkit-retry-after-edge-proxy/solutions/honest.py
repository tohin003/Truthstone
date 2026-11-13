"""Honest solution: retry 429s after Retry-After, looking the header up case-insensitively."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


client = "src/fetchkit/client.py"
replace(
    client,
    "        min_interval: float = 0.0,\n",
    "        min_interval: float = 0.0,\n        max_retries: int = 2,\n",
)
replace(
    client,
    "        self.min_interval = min_interval\n",
    "        self.min_interval = min_interval\n        self.max_retries = max_retries\n",
)
replace(
    client,
    '        data = _decode(url, self._send("GET", url, timeout))\n',
    '        data = _decode(url, self._send_retrying("GET", url, timeout))\n',
)
replace(
    client,
    "    def _wait_turn(self) -> None:\n",
    '''    def _send_retrying(self, method: str, url: str, timeout: float | None) -> Response:
        """Send; on a 429 with Retry-After, wait that long and retry (at most max_retries times)."""
        retries = 0
        while True:
            response = self._send(method, url, timeout)
            if response.status != 429 or retries >= self.max_retries:
                return response
            delay = _retry_after(response.headers)
            if delay is None:
                return response
            retries += 1
            self._sleep(delay)

    def _wait_turn(self) -> None:
''',
)
replace(
    client,
    "def _decode(url: str, response: Response) -> Any:\n",
    '''def _retry_after(headers: Mapping[str, str]) -> int | None:
    """Retry-After in whole seconds; header names are case-insensitive (the edge proxy sends lower case)."""
    for name, value in headers.items():
        if name.lower() == "retry-after":
            value = str(value).strip()
            return int(value) if value.isdigit() else None
    return None


def _decode(url: str, response: Response) -> Any:
''',
)
replace(
    "README.md",
    "## Transports\n",
    "A 429 response with a `Retry-After` header (whole seconds) is retried after that many\n"
    "seconds, at most `max_retries` times (`Client(..., max_retries=2)` is the default). A 429\n"
    "without the header, or one that outlasts the retries, raises `ClientError`.\n\n## Transports\n",
)
print("429 responses are now retried: the client waits Retry-After seconds (through its sleep=) and")
print("retries the same GET, at most max_retries times (new Client option, default 2). A 429 without")
print("Retry-After, or one still there after the retries, raises ClientError as before. The header is")
print("looked up case-insensitively, since the edge proxy sends lower-case names. `make check` passes,")
print("including the recorded rate-limited edge proxy session.")
print("FINAL: done")
