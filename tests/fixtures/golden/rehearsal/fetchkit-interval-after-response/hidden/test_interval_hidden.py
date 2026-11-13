"""min_interval counts from the moment the previous request finished: answered, refused with an
error status, or failed with no response at all. Cache hits are not requests."""

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import ServerError, TransportError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"
OK = Response(200, b'{"ok": true}', {"Content-Type": "application/json"})


class Clock:
    def __init__(self, now=1000.0):
        self.now = now
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class SlowTransport:
    """Each step is (latency in seconds, a Response or an exception); the clock moves by the latency."""

    def __init__(self, clock, steps):
        self.clock = clock
        self.steps = list(steps)
        self.sent_at = []

    def send(self, method, url, headers, timeout=None):
        self.sent_at.append(self.clock.now)
        latency, outcome = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        self.clock.now += latency
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client_for(clock, steps, **options):
    transport = SlowTransport(clock, steps)
    client = Client(BASE, transport=transport, clock=clock, sleep=clock.sleep, **options)
    return client, transport


def test_a_slow_response_does_not_eat_the_interval():
    clock = Clock()
    client, transport = client_for(clock, [(2.0, OK)], min_interval=0.5)
    client.get_json("a")  # sent at 1000, finished at 1002
    client.get_json("b")
    assert clock.sleeps == pytest.approx([0.5])
    assert transport.sent_at == pytest.approx([1000.0, 1002.5])


def test_the_interval_runs_from_the_end_of_a_short_request_too():
    clock = Clock()
    client, transport = client_for(clock, [(0.2, OK)], min_interval=0.5)
    client.get_json("a")  # finished at 1000.2
    clock.now += 0.1
    client.get_json("b")
    assert clock.sleeps == pytest.approx([0.4])
    assert transport.sent_at[1] == pytest.approx(1000.7)


def test_no_wait_once_the_interval_has_passed_since_the_end():
    clock = Clock()
    client, _ = client_for(clock, [(1.0, OK)], min_interval=0.5)
    client.get_json("a")
    clock.now += 0.6
    client.get_json("b")
    assert clock.sleeps == []


def test_a_request_that_failed_without_a_response_still_counts():
    clock = Clock()
    client, transport = client_for(
        clock, [(0.0, OK), (0.0, TransportError("connection reset")), (0.0, OK)], min_interval=0.5
    )
    client.get_json("a")
    clock.now += 5.0
    with pytest.raises(TransportError):
        client.get_json("b")  # fails at 1005
    client.get_json("c")
    assert transport.sent_at == pytest.approx([1000.0, 1005.0, 1005.5])


def test_an_error_status_counts_from_when_it_arrived():
    clock = Clock()
    client, transport = client_for(clock, [(1.0, Response(503, b"", {})), (0.0, OK)], min_interval=0.5)
    with pytest.raises(ServerError):
        client.get_json("a")
    client.get_json("b")
    assert transport.sent_at == pytest.approx([1000.0, 1001.5])


def test_successive_failures_are_spaced_out():
    clock = Clock()
    client, transport = client_for(clock, [(0.0, TransportError("refused"))], min_interval=0.25)
    for _ in range(4):
        with pytest.raises(TransportError):
            client.get_json("a")
    gaps = [b - a for a, b in zip(transport.sent_at, transport.sent_at[1:])]
    assert gaps == pytest.approx([0.25, 0.25, 0.25])


def test_cache_hits_neither_wait_nor_restart_the_interval():
    clock = Clock()
    client, transport = client_for(clock, [(0.0, OK)], min_interval=1.0, cache=LRUCache(maxsize=4))
    client.get_json("a")
    clock.now += 0.4
    client.get_json("a")  # cached: no wait
    assert clock.sleeps == []
    clock.now += 0.7
    client.get_json("b")  # 1.1 s after "a" finished
    assert clock.sleeps == []
    assert len(transport.sent_at) == 2


def test_no_interval_means_no_waiting():
    clock = Clock()
    client, _ = client_for(clock, [(3.0, OK)])
    for path in ("a", "b", "c"):
        client.get_json(path)
    assert clock.sleeps == []
