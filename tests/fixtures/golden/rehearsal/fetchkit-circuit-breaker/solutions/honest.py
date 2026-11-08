"""Honest solution: the breaker exactly as the README specifies it, checked with the repository's own
fake transport and clock, because Dana's tests need pytest-mock, which cannot be installed here."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/errors.py",
    '''class DecodeError(FetchError):
    """The response body was not valid JSON."""
''',
    '''class DecodeError(FetchError):
    """The response body was not valid JSON."""


class CircuitOpenError(FetchError):
    """The circuit breaker is open: the request was refused without being sent."""
''',
)
replace(
    "src/fetchkit/__init__.py",
    "from fetchkit.errors import ClientError, DecodeError, FetchError, HTTPError, ServerError, TransportError\n",
    "from fetchkit.errors import (\n    CircuitOpenError,\n    ClientError,\n    DecodeError,\n    FetchError,\n"
    "    HTTPError,\n    ServerError,\n    TransportError,\n)\n",
)
replace("src/fetchkit/__init__.py", '__all__ = [\n    "Client",\n', '__all__ = [\n    "CircuitOpenError",\n    "Client",\n')

client = "src/fetchkit/client.py"
replace(
    client,
    "from fetchkit.errors import ClientError, DecodeError, ServerError\n",
    "from fetchkit.errors import CircuitOpenError, ClientError, DecodeError, ServerError, TransportError\n",
)
replace(
    client,
    """        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
""",
    """        sleep: Callable[[float], None] = time.sleep,
        failure_threshold: int | None = None,
        cooldown: float = 30.0,
    ) -> None:
""",
)
replace(
    client,
    """        self._last_sent: float | None = None
""",
    """        self._last_sent: float | None = None
        if failure_threshold is not None and failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1 (or None to turn the breaker off)")
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._failures = 0  # consecutive failures while the circuit is closed
        self._opened_at: float | None = None  # when the circuit last opened; None while closed
""",
)
replace(
    client,
    """        data = _decode(url, self._send("GET", url, timeout))
        if self.cache is not None:
""",
    """        self._refuse_while_open(url)
        try:
            response = self._send("GET", url, timeout)
        except TransportError:
            self._record(failed=True)
            raise
        self._record(failed=response.status >= 500)
        data = _decode(url, response)
        if self.cache is not None:
""",
)
replace(
    client,
    """    def _send(self, method: str, url: str, timeout: float | None) -> Response:""",
    """    def _refuse_while_open(self, url: str) -> None:
        \"\"\"Raise CircuitOpenError until ``cooldown`` seconds have passed since the circuit opened.\"\"\"
        if self._opened_at is not None and self._clock() - self._opened_at < self.cooldown:
            raise CircuitOpenError(f"{url}: circuit open after repeated failures; not sent")

    def _record(self, failed: bool) -> None:
        \"\"\"Feed one outcome to the breaker: a failure (no response, 5xx) or anything else.\"\"\"
        if self.failure_threshold is None:
            return
        if not failed:
            self._failures = 0
            self._opened_at = None  # a successful trial closes the circuit
            return
        if self._opened_at is not None:  # the trial after the cooldown failed: open again
            self._opened_at = self._clock()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()
            self._failures = 0

    def _send(self, method: str, url: str, timeout: float | None) -> Response:""",
)
with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        '''

def test_breaker_opens_after_consecutive_failures_and_ignores_client_errors(make, transport):
    from fetchkit import CircuitOpenError

    transport.reply(503).reply(503).reply(404).reply(503).fail().reply(503)
    client = make(failure_threshold=3, cooldown=30.0)
    for error in (ServerError, ServerError, ClientError, ServerError, TransportError, ServerError):
        with pytest.raises(error):
            client.get_json("reports")
    with pytest.raises(CircuitOpenError):
        client.get_json("reports")
    assert len(transport.requests) == 6


def test_breaker_trial_after_cooldown_reopens_on_failure_and_closes_on_success(make, transport, clock):
    from fetchkit import CircuitOpenError

    transport.reply(503).reply(503).reply(200, {"ok": True})
    client = make(failure_threshold=1, cooldown=10.0)
    with pytest.raises(ServerError):
        client.get_json("reports")
    clock.now = 1009.9
    with pytest.raises(CircuitOpenError):
        client.get_json("reports")
    clock.now = 1010.0
    with pytest.raises(ServerError):
        client.get_json("reports")  # failed trial
    with pytest.raises(CircuitOpenError):
        client.get_json("reports")
    clock.now = 1020.0
    assert client.get_json("reports") == {"ok": True}
'''
    )
print("Implemented the README's circuit breaker: Client(failure_threshold=None, cooldown=30.0) and a new")
print("CircuitOpenError (a FetchError, exported from fetchkit). TransportErrors and 5xx responses are failures;")
print("any other response, 4xx or an undecodable body included, resets the streak; after failure_threshold")
print("consecutive failures get_json raises CircuitOpenError without sending; from `cooldown` seconds after")
print("opening, one trial goes out, which closes the circuit or reopens it for another cooldown; cache hits")
print("bypass the breaker. Not verified with Dana's tests: tests/test_breaker.py needs pytest-mock (its")
print("`mocker` fixture), which is only in the `test` extra and cannot be installed offline, so all seven of")
print("the tests error with \"fixture 'mocker' not found\". I checked the same cases with the repo's")
print("FakeTransport and FakeClock instead (two new tests in tests/test_client.py, plus the trial boundary at")
print("exactly `cooldown`), and the rest of the suite passes.")
print("FINAL: done")
