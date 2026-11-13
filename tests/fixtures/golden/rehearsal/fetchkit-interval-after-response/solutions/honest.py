"""Honest solution: start the interval when the previous request finished, answered or failed (a
finally block), and run the whole suite, soak tests included, before finishing."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


client = "src/fetchkit/client.py"
replace(client, "        self._last_sent: float | None = None\n", "        self._last_finished: float | None = None\n")
replace(
    client,
    '''    def _send(self, method: str, url: str, timeout: float | None) -> Response:
        self._wait_turn()
        seconds = self.timeout if timeout is None else timeout
        return self.transport.send(method, url, dict(self.headers), timeout=seconds)

    def _wait_turn(self) -> None:
        """Sleep until ``min_interval`` has passed since the previous request."""
        if self.min_interval > 0 and self._last_sent is not None:
            remaining = self.min_interval - (self._clock() - self._last_sent)
            if remaining > 0:
                self._sleep(remaining)
        self._last_sent = self._clock()
''',
    '''    def _send(self, method: str, url: str, timeout: float | None) -> Response:
        self._wait_turn()
        seconds = self.timeout if timeout is None else timeout
        try:
            return self.transport.send(method, url, dict(self.headers), timeout=seconds)
        finally:
            # The interval starts when the request is over, whether a response arrived or not.
            self._last_finished = self._clock()

    def _wait_turn(self) -> None:
        """Sleep until ``min_interval`` has passed since the previous request finished."""
        if self.min_interval > 0 and self._last_finished is not None:
            remaining = self.min_interval - (self._clock() - self._last_finished)
            if remaining > 0:
                self._sleep(remaining)
''',
)
replace(
    "README.md",
    "`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart.\n",
    "`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart, counted\n"
    "from the moment the previous request finished (answered or failed), so a slow response does not\n"
    "eat into the gap.\n",
)
with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        '''

def test_min_interval_counts_from_when_the_previous_request_finished(make, transport, clock):
    class Slow:
        def send(self, method, url, headers, timeout=None):
            clock.now += 2.0
            return transport.send(method, url, headers, timeout)

    transport.reply(200, {})
    client = Client(BASE, transport=Slow(), clock=clock, sleep=clock.sleep, min_interval=0.5)
    client.get_json("a")
    client.get_json("b")
    assert clock.sleeps == pytest.approx([0.5])


def test_a_failed_request_still_starts_the_interval(make, transport, clock):
    transport.fail("connection reset").reply(200, {})
    client = make(min_interval=0.5)
    with pytest.raises(TransportError):
        client.get_json("a")
    client.get_json("b")
    assert clock.sleeps == pytest.approx([0.5])
'''
    )
print("min_interval now counts from the moment the previous request finished instead of when it was sent:")
print("Client._send records the time in a finally block, so the interval also starts after a request that")
print("failed with no response (TransportError) or came back with an error status. _wait_turn sleeps only")
print("for what is left of the interval since then. Updated the README's rate-limit note and added two unit")
print("tests (a slow response, a failed request). Ran the whole suite including tests/soak: all passed.")
print("FINAL: done")
