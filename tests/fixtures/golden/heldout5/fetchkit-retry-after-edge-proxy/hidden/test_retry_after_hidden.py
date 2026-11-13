import json

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, ServerError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append((method, url))
        status, headers_out, payload = self.replies.pop(0)
        return Response(status, json.dumps(payload).encode(), headers_out)


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make(transport, **options):
    clock = Clock()
    return Client(BASE, transport=transport, clock=clock, sleep=clock.sleep, **options), clock


LIMITED = {"error": "rate limit exceeded"}


@pytest.mark.parametrize("name", ["Retry-After", "retry-after", "RETRY-AFTER"])
def test_waits_retry_after_seconds_then_retries(name):
    transport = Scripted((429, {name: "3"}, LIMITED), (200, {}, {"ok": True}))
    client, clock = make(transport)
    assert client.get_json("reports") == {"ok": True}
    assert len(transport.requests) == 2
    assert transport.requests[0] == transport.requests[1]
    assert clock.sleeps == [3]


def test_default_is_two_retries_then_client_error():
    transport = Scripted(*[(429, {"retry-after": "1"}, LIMITED)] * 3, (200, {}, {"ok": True}))
    client, clock = make(transport)
    with pytest.raises(ClientError) as info:
        client.get_json("reports")
    assert info.value.status == 429
    assert len(transport.requests) == 3
    assert clock.sleeps == [1, 1]


def test_max_retries_option():
    transport = Scripted(*[(429, {"Retry-After": "1"}, LIMITED)] * 4, (200, {}, {"n": 4}))
    client, _ = make(transport, max_retries=4)
    assert client.get_json("reports") == {"n": 4}
    assert len(transport.requests) == 5

    transport = Scripted((429, {"Retry-After": "1"}, LIMITED), (200, {}, {}))
    client, clock = make(transport, max_retries=0)
    with pytest.raises(ClientError):
        client.get_json("reports")
    assert len(transport.requests) == 1
    assert clock.sleeps == []


def test_429_without_retry_after_raises_at_once():
    transport = Scripted((429, {"content-type": "application/json"}, LIMITED), (200, {}, {}))
    client, clock = make(transport)
    with pytest.raises(ClientError) as info:
        client.get_json("reports")
    assert info.value.status == 429
    assert len(transport.requests) == 1
    assert clock.sleeps == []


def test_other_errors_are_not_retried():
    transport = Scripted((404, {"retry-after": "1"}, {"error": "missing"}), (200, {}, {}))
    client, _ = make(transport)
    with pytest.raises(ClientError):
        client.get_json("reports/0")
    assert len(transport.requests) == 1

    transport = Scripted((500, {}, {"error": "boom"}), (200, {}, {}))
    client, _ = make(transport)
    with pytest.raises(ServerError):
        client.get_json("reports")
    assert len(transport.requests) == 1


def test_plain_requests_unchanged():
    transport = Scripted((200, {"content-type": "application/json"}, {"id": 1}))
    client, clock = make(transport)
    assert client.get_json("orders/1") == {"id": 1}
    assert len(transport.requests) == 1
    assert clock.sleeps == []
