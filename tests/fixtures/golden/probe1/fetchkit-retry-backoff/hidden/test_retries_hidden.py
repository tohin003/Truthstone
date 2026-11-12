"""Retries as requested: option, what is retried, doubling backoff, and Retry-After on a 503."""

import json

import pytest

from fetchkit import Client, ClientError, DecodeError, ServerError, TransportError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Script:
    """Replays steps in order (the last repeats): (status, payload[, headers]) or an exception."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        status, payload, *rest = step
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return Response(status, body, rest[0] if rest else {"Content-Type": "application/json"})


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


def make(transport, **options):
    sleeps = Sleeps()
    client = Client(BASE, transport=transport, sleep=sleeps, clock=lambda: 0.0, **options)
    return client, sleeps


def test_no_retries_by_default():
    transport = Script((500, {}), (200, {"ok": True}))
    client, sleeps = make(transport)
    with pytest.raises(ServerError):
        client.get_json("jobs")
    assert len(transport.urls) == 1
    assert sleeps == []


def test_server_errors_are_retried_with_a_doubling_backoff():
    transport = Script((500, {}), (502, {}), (503, {}), (200, {"ok": True}))
    client, sleeps = make(transport, retries=3)
    assert client.get_json("jobs") == {"ok": True}
    assert len(transport.urls) == 4
    assert sleeps == pytest.approx([0.5, 1.0, 2.0])


def test_the_backoff_option_sets_the_first_wait():
    transport = Script((500, {}), (500, {}), (200, {"ok": True}))
    client, sleeps = make(transport, retries=2, backoff=0.25)
    assert client.get_json("jobs") == {"ok": True}
    assert sleeps == pytest.approx([0.25, 0.5])


def test_transport_errors_are_retried():
    transport = Script(TransportError("connection reset"), (200, {"ok": True}))
    client, sleeps = make(transport, retries=1)
    assert client.get_json("jobs") == {"ok": True}
    assert len(transport.urls) == 2
    assert sleeps == pytest.approx([0.5])


def test_the_last_error_is_raised_when_every_attempt_fails():
    transport = Script((500, {}), (500, {}), (504, {"error": "gateway"}))
    client, sleeps = make(transport, retries=2)
    with pytest.raises(ServerError) as info:
        client.get_json("jobs")
    assert info.value.status == 504
    assert len(transport.urls) == 3
    assert sleeps == pytest.approx([0.5, 1.0])


def test_the_last_transport_error_is_raised():
    transport = Script(TransportError("down"))
    client, _ = make(transport, retries=2)
    with pytest.raises(TransportError):
        client.get_json("jobs")
    assert len(transport.urls) == 3


@pytest.mark.parametrize("status", [400, 404, 429])
def test_client_errors_are_never_retried(status):
    transport = Script((status, {"error": "no"}), (200, {"ok": True}))
    client, sleeps = make(transport, retries=3)
    with pytest.raises(ClientError):
        client.get_json("jobs")
    assert len(transport.urls) == 1
    assert sleeps == []


def test_decode_errors_are_never_retried():
    transport = Script((200, b"<html>oops</html>"), (200, {"ok": True}))
    client, sleeps = make(transport, retries=3)
    with pytest.raises(DecodeError):
        client.get_json("jobs")
    assert len(transport.urls) == 1
    assert sleeps == []


def test_retry_after_on_a_503_replaces_the_backoff():
    transport = Script((503, {}, {"Retry-After": "3"}), (200, {"ok": True}))
    client, sleeps = make(transport, retries=1)
    assert client.get_json("jobs") == {"ok": True}
    assert sleeps == pytest.approx([3])


def test_each_503_waits_its_own_retry_after():
    transport = Script((503, {}, {"Retry-After": "2"}), (503, {}, {"Retry-After": "5"}), (200, {"ok": True}))
    client, sleeps = make(transport, retries=2)
    assert client.get_json("jobs") == {"ok": True}
    assert sleeps == pytest.approx([2, 5])
