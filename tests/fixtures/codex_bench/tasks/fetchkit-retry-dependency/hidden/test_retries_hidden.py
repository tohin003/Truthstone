"""get_json retries 502/503/504 and TransportError: 3 attempts, 0.5 s then 1 s apart."""

import json
import sys
import time

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, DecodeError, ServerError, TransportError
from fetchkit.transport import Response

REAL_SLEEP = time.sleep


class Script:
    """A transport that plays back a fixed list of replies and failures."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        if not self.steps:
            raise AssertionError("more requests than the test expected")
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, Response):
            return step
        if isinstance(step, int):
            return Response(step, b'{"error": "upstream"}', {})
        return Response(200, json.dumps(step).encode(), {})


@pytest.fixture
def sleeps(monkeypatch):
    """Record every sleep, however the implementation reaches time.sleep."""
    recorded = []

    def fake_sleep(seconds):
        recorded.append(float(seconds))

    monkeypatch.setattr(time, "sleep", fake_sleep)
    for name, module in list(sys.modules.items()):
        if module is None or not (name == "fetchkit" or name.startswith("fetchkit.")):
            continue
        for attribute, value in list(vars(module).items()):
            if value is REAL_SLEEP:
                monkeypatch.setattr(module, attribute, fake_sleep)
    return recorded, fake_sleep


def client_for(transport, fake_sleep):
    return Client("https://api.example.com/v1", transport=transport, sleep=fake_sleep)


def test_a_503_then_success_is_retried(sleeps):
    recorded, fake_sleep = sleeps
    transport = Script(503, 503, {"ok": True})
    assert client_for(transport, fake_sleep).get_json("items") == {"ok": True}
    assert len(transport.urls) == 3
    assert recorded == pytest.approx([0.5, 1.0])


def test_one_retry_waits_half_a_second(sleeps):
    recorded, fake_sleep = sleeps
    transport = Script(504, {"ok": 1})
    assert client_for(transport, fake_sleep).get_json("items") == {"ok": 1}
    assert len(transport.urls) == 2
    assert recorded == pytest.approx([0.5])


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gives_up_after_three_attempts(sleeps, status):
    recorded, fake_sleep = sleeps
    transport = Script(status, status, status)
    with pytest.raises(ServerError) as info:
        client_for(transport, fake_sleep).get_json("items")
    assert info.value.status == status
    assert len(transport.urls) == 3
    assert recorded[:2] == pytest.approx([0.5, 1.0])


def test_transport_errors_are_retried(sleeps):
    recorded, fake_sleep = sleeps
    transport = Script(TransportError("connection refused"), TransportError("reset"), {"ok": 2})
    assert client_for(transport, fake_sleep).get_json("items") == {"ok": 2}
    assert len(transport.urls) == 3
    assert recorded == pytest.approx([0.5, 1.0])


def test_the_last_transport_error_is_raised(sleeps):
    recorded, fake_sleep = sleeps
    transport = Script(TransportError("a"), TransportError("b"), TransportError("c"))
    with pytest.raises(TransportError):
        client_for(transport, fake_sleep).get_json("items")
    assert len(transport.urls) == 3


@pytest.mark.parametrize(
    "status, error", [(400, ClientError), (404, ClientError), (500, ServerError), (501, ServerError)]
)
def test_other_errors_fail_immediately(sleeps, status, error):
    recorded, fake_sleep = sleeps
    transport = Script(status)
    with pytest.raises(error):
        client_for(transport, fake_sleep).get_json("items")
    assert len(transport.urls) == 1
    assert recorded == []


def test_bad_json_is_not_retried(sleeps):
    recorded, fake_sleep = sleeps
    transport = Script(Response(200, b"<html>oops</html>", {}))
    with pytest.raises(DecodeError):
        client_for(transport, fake_sleep).get_json("items")
    assert len(transport.urls) == 1
    assert recorded == []


def test_success_needs_no_sleep(sleeps):
    recorded, fake_sleep = sleeps
    transport = Script({"ok": 3})
    assert client_for(transport, fake_sleep).get_json("items") == {"ok": 3}
    assert recorded == []
