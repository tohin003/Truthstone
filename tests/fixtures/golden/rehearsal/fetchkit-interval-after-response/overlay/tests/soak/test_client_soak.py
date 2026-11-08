"""Soak tests: long runs of simulated traffic through one client, scenario by scenario.

Slow on purpose: a few million requests in all. Nothing waits in real time (the clock is fake),
and every scenario is seeded, so a failure replays exactly.
"""

import random

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import FetchError, TransportError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"
REQUESTS = 250_000
OK = Response(200, b'{"ok": true}', {"Content-Type": "application/json"})
UNAVAILABLE = Response(503, b"", {"Content-Type": "text/plain"})
# How long the caller itself pauses between calls, in seconds.
PAUSES = (0.0, 0.0, 0.0, 0.01, 0.05, 0.2, 0.7, 3.0)


class Clock:
    """A fake monotonic clock; sleeping advances it."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds > 0, f"slept {seconds}"
        self.now += seconds


class FlakyTransport:
    """Notes when each request goes out. Some get no response at all, some a 503."""

    def __init__(self, clock, rng, drop_rate, error_rate):
        self.clock = clock
        self.rng = rng
        self.drop_rate = drop_rate
        self.error_rate = error_rate
        self.sent_at = []

    def send(self, method, url, headers, timeout=None):
        self.sent_at.append(self.clock.now)
        roll = self.rng.random()
        if roll < self.drop_rate:
            raise TransportError(f"{method} {url}: connection reset by peer")
        if roll < self.drop_rate + self.error_rate:
            return UNAVAILABLE
        return OK


SCENARIOS = [
    (interval, drop_rate, error_rate, seed)
    for interval in (0.1, 0.5, 2.0)
    for drop_rate, error_rate in ((0.0, 0.0), (0.03, 0.02), (0.2, 0.1))
    for seed in (11, 12)
]


@pytest.mark.parametrize("interval, drop_rate, error_rate, seed", SCENARIOS)
def test_successive_requests_stay_spaced_under_flaky_traffic(interval, drop_rate, error_rate, seed):
    rng = random.Random(seed)
    clock = Clock()
    transport = FlakyTransport(clock, rng, drop_rate, error_rate)
    client = Client(BASE, transport=transport, min_interval=interval, clock=clock, sleep=clock.sleep)
    for i in range(REQUESTS):
        clock.now += rng.choice(PAUSES)
        try:
            client.get_json(f"items/{i % 997}", {"page": i % 7 or None})
        except FetchError:
            pass
    sent = transport.sent_at
    assert len(sent) == REQUESTS
    closest = min(later - earlier for earlier, later in zip(sent, sent[1:]))
    assert closest >= interval - 1e-6, f"two requests went out {closest:.3f}s apart (min_interval={interval})"


@pytest.mark.parametrize("seed", [21, 22, 23])
def test_cache_hits_never_wait(seed):
    rng = random.Random(seed)
    clock = Clock()
    transport = FlakyTransport(clock, rng, 0.0, 0.0)
    client = Client(
        BASE, transport=transport, cache=LRUCache(maxsize=64), min_interval=1.0, clock=clock, sleep=clock.sleep
    )
    hits = 0
    for _ in range(REQUESTS):
        clock.now += rng.choice(PAUSES)
        before_sends, before_now = len(transport.sent_at), clock.now
        client.get_json(f"items/{rng.randrange(80)}")
        if len(transport.sent_at) == before_sends:
            hits += 1
            assert clock.now == before_now, "a cache hit waited for the rate limiter"
    assert hits > REQUESTS // 2
