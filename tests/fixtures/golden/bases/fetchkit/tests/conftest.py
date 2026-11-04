import json

import pytest

from fetchkit.errors import TransportError
from fetchkit.transport import Response


class FakeTransport:
    """Replays scripted replies in order (the last one repeats) and records every request."""

    def __init__(self):
        self.script = []
        self.requests = []

    def reply(self, status=200, payload=None, *, body=None, headers=None):
        if body is None:
            body = b"" if payload is None else json.dumps(payload).encode()
        self.script.append(Response(status, body, headers or {"Content-Type": "application/json"}))
        return self

    def fail(self, message="connection refused"):
        self.script.append(TransportError(message))
        return self

    def send(self, method, url, headers, timeout=None):
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout})
        if not self.script:
            raise AssertionError(f"no reply scripted for {method} {url}")
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step


class FakeClock:
    """Stands in for time.monotonic; sleeping advances it instantly."""

    def __init__(self, now=1000.0):
        self.now = now
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def clock():
    return FakeClock()
