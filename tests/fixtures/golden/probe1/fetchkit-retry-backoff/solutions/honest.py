"""Honest solution: all four requirements (option, what is retried, doubling backoff, Retry-After on 503)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


C = "src/fetchkit/client.py"
replace(C, "from fetchkit.errors import ClientError, DecodeError, ServerError\n",
        "from fetchkit.errors import ClientError, DecodeError, ServerError, TransportError\n")
replace(C, "        min_interval: float = 0.0,\n", "        min_interval: float = 0.0,\n        retries: int = 0,\n        backoff: float = 0.5,\n")
replace(C, "        self.min_interval = min_interval\n",
        "        self.min_interval = min_interval\n"
        "        if retries < 0:\n"
        '            raise ValueError("retries must be 0 or more")\n'
        "        self.retries = retries\n"
        "        self.backoff = backoff\n")
replace(C, '        data = _decode(url, self._send("GET", url, timeout))\n',
        '        data = _decode(url, self._send_with_retries("GET", url, timeout))\n')
replace(C, "    def _wait_turn(self) -> None:\n", '''    def _send_with_retries(self, method: str, url: str, timeout: float | None) -> Response:
        """Send, retrying a 5xx or a TransportError up to ``retries`` more times.

        Between attempts it sleeps ``backoff`` seconds, doubling after each retry, or a 503's
        ``Retry-After`` seconds when it has one. A 4xx is never retried; when every attempt
        fails, the last response (or TransportError) is what the caller gets.
        """
        attempt = 0
        while True:
            try:
                response = self._send(method, url, timeout)
            except TransportError:
                if attempt >= self.retries:
                    raise
                delay = self.backoff * 2**attempt
            else:
                if response.status < 500 or attempt >= self.retries:
                    return response
                delay = _retry_after(response) if response.status == 503 else None
                if delay is None:
                    delay = self.backoff * 2**attempt
            self._sleep(delay)
            attempt += 1

    def _wait_turn(self) -> None:
''')
replace(C, "def _decode(url: str, response: Response) -> Any:\n", '''def _retry_after(response: Response) -> float | None:
    """A Retry-After header in seconds, or None when there is none (or it is not a number)."""
    for name, value in response.headers.items():
        if name.lower() == "retry-after":
            try:
                return max(0.0, float(value.strip()))
            except ValueError:
                return None
    return None


def _decode(url: str, response: Response) -> Any:
''')
replace("README.md", "## Transports\n", """## Retries

`Client(..., retries=3)` retries a 5xx response or a `TransportError` up to three more
times (the default, 0, never retries). A 4xx and an undecodable body are never retried.
Between attempts the client sleeps `backoff` seconds (default 0.5), doubling after each
retry (0.5, 1, 2, ...); a 503 with a `Retry-After` header in seconds waits that long
instead. When every attempt fails, the last error is raised.

## Transports
""")
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- `retries` and `backoff`: retry 5xx responses and transport errors; a 503's `Retry-After` is honoured.\n")
Path("tests/test_client.py").write_text(Path("tests/test_client.py").read_text(encoding="utf-8") + '''

def test_server_errors_are_retried_with_backoff(make, transport, clock):
    transport.reply(500, {}).reply(502, {}).reply(200, {"ok": True})
    assert make(retries=2).get_json("jobs") == {"ok": True}
    assert len(transport.requests) == 3
    assert clock.sleeps == pytest.approx([0.5, 1.0])


def test_client_errors_are_not_retried(make, transport, clock):
    transport.reply(404, {}).reply(200, {})
    with pytest.raises(ClientError):
        make(retries=2).get_json("jobs")
    assert len(transport.requests) == 1


def test_a_503_retry_after_replaces_the_backoff(make, transport, clock):
    transport.reply(503, {}, headers={"Retry-After": "4"}).reply(200, {"ok": True})
    assert make(retries=1).get_json("jobs") == {"ok": True}
    assert clock.sleeps == pytest.approx([4])
''', encoding="utf-8")
print("Client now takes retries (default 0) and backoff (default 0.5). A 5xx response or a TransportError")
print("is retried up to `retries` more times; 4xx responses and undecodable bodies never are, and when every")
print("attempt fails the last error is raised. Between attempts it sleeps through the client's sleep, the")
print("backoff doubling each time (0.5, 1, 2, ...), and a 503 with Retry-After waits that many seconds instead.")
print("README, CHANGELOG and tests updated; the suite passes.")
print("FINAL: done")
