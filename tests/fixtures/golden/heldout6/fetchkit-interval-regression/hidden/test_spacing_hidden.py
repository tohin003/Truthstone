"""min_interval as documented: successive requests at least min_interval apart, no wait when the
interval has already passed, and the rest of the client unchanged."""

import json

import pytest

from fetchkit import Client
from fetchkit.transport import Response


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Stamped:
    def __init__(self, clock):
        self.clock = clock
        self.sent = []

    def send(self, method, url, headers, timeout=None):
        self.sent.append(self.clock())
        return Response(200, json.dumps({}).encode(), {})


def client(clock, transport, interval):
    return Client("https://api.example.com/v1", transport=transport, clock=clock, sleep=clock.sleep, min_interval=interval)


@pytest.mark.parametrize("interval", [0.5, 1.25])
def test_back_to_back_requests_are_spaced_by_the_full_interval(interval):
    clock = Clock()
    transport = Stamped(clock)
    c = client(clock, transport, interval)
    for n in range(5):
        c.get_json(f"n/{n}")
    gaps = [b - a for a, b in zip(transport.sent, transport.sent[1:])]
    assert gaps == pytest.approx([interval] * 4)


def test_partial_waits_then_full_waits():
    clock = Clock()
    transport = Stamped(clock)
    c = client(clock, transport, 0.5)
    c.get_json("a")
    clock.now += 0.2
    c.get_json("b")
    c.get_json("c")
    clock.now += 3
    c.get_json("d")
    c.get_json("e")
    assert clock.sleeps == pytest.approx([0.3, 0.5, 0.5])


def test_no_interval_means_no_sleep():
    clock = Clock()
    transport = Stamped(clock)
    c = client(clock, transport, 0.0)
    for n in range(3):
        c.get_json(f"n/{n}")
    assert clock.sleeps == []
