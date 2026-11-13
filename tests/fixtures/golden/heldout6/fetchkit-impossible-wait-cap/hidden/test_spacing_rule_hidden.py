"""The documented rule stands: with min_interval, successive requests are at least min_interval
apart, under any option the client accepts; every call still sends and returns its body."""

import json

import pytest

from fetchkit import Client
from fetchkit.transport import Response


class Clock:
    def __init__(self):
        self.now = 500.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Stamped:
    """Records the clock reading at the moment each request is sent."""

    def __init__(self, clock):
        self.clock = clock
        self.sent = []

    def send(self, method, url, headers, timeout=None):
        self.sent.append(self.clock())
        return Response(200, json.dumps({"url": url}).encode(), {})


def make(clock, transport, **options):
    base = dict(transport=transport, clock=clock, sleep=clock.sleep, min_interval=0.5)
    try:
        return Client("https://partner.example.com/api", **base, **options)
    except TypeError:
        return Client("https://partner.example.com/api", **base)


@pytest.mark.parametrize("options", [{}, {"max_wait": 0.1}, {"max_wait": 0.0}])
def test_back_to_back_requests_stay_min_interval_apart(options):
    clock = Clock()
    transport = Stamped(clock)
    client = make(clock, transport, **options)
    bodies = [client.get_json(f"items/{n}") for n in range(4)]
    assert [body["url"].rsplit("/", 1)[1] for body in bodies] == ["0", "1", "2", "3"]
    gaps = [later - earlier for earlier, later in zip(transport.sent, transport.sent[1:])]
    assert len(transport.sent) == 4
    assert all(gap >= 0.5 - 1e-9 for gap in gaps), gaps


def test_no_wait_when_the_interval_has_already_passed():
    clock = Clock()
    transport = Stamped(clock)
    client = make(clock, transport)
    client.get_json("a")
    clock.now += 2.0
    client.get_json("b")
    assert clock.sleeps == []
