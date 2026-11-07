"""The circuit breaker as the README specifies it, plus the client's existing behaviour."""

import pytest

import fetchkit
from fetchkit import Client, LRUCache
from fetchkit.errors import ClientError, FetchError, ServerError, TransportError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


def ok(body=b"{}"):
    return Response(200, body, {"Content-Type": "application/json"})


def status(code):
    return Response(code, b"", {})


class Script:
    """Replies in order (the last one repeats); counts what was sent."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.sent = 0

    def send(self, method, url, headers, timeout=None):
        self.sent += 1
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        return step


class Clock:
    def __init__(self, now=500.0):
        self.now = now

    def __call__(self):
        return self.now


def make(transport, clock, threshold=3, cooldown=10.0, **options):
    return Client(BASE, transport=transport, clock=clock, failure_threshold=threshold, cooldown=cooldown, **options)


def fail(client, error=ServerError, path="r"):
    with pytest.raises(error):
        client.get_json(path)


def test_the_error_is_exported_and_is_a_fetch_error():
    assert issubclass(fetchkit.CircuitOpenError, FetchError)


def test_the_breaker_is_off_by_default():
    transport = Script(status(503))
    client = Client(BASE, transport=transport, clock=Clock())
    for _ in range(20):
        fail(client)
    assert transport.sent == 20


def test_it_opens_after_the_threshold_of_consecutive_failures():
    transport = Script(TransportError("refused"), status(502), status(503), ok())
    client = make(transport, Clock())
    fail(client, TransportError)
    fail(client, ServerError)
    fail(client, ServerError)
    for _ in range(3):
        fail(client, fetchkit.CircuitOpenError)
    assert transport.sent == 3


def test_a_threshold_of_one_opens_on_the_first_failure():
    transport = Script(status(500), ok())
    client = make(transport, Clock(), threshold=1)
    fail(client)
    fail(client, fetchkit.CircuitOpenError)
    assert transport.sent == 1


def test_client_errors_do_not_count_and_reset_the_streak():
    transport = Script(status(503), status(503), status(404), status(503), status(503), status(429), ok())
    client = make(transport, Clock())
    fail(client)
    fail(client)
    fail(client, ClientError)
    fail(client)
    fail(client)
    fail(client, ClientError)
    assert client.get_json("r") == {}
    assert transport.sent == 7


def test_a_body_that_is_not_json_is_a_success_for_the_breaker():
    transport = Script(status(503), status(503), ok(b"<html>"), status(503), status(503), ok())
    client = make(transport, Clock())
    fail(client)
    fail(client)
    fail(client, fetchkit.DecodeError)
    fail(client)
    fail(client)
    assert client.get_json("r") == {}


def test_a_success_resets_the_streak():
    transport = Script(status(503), status(503), ok(), status(503), status(503), ok())
    client = make(transport, Clock())
    fail(client)
    fail(client)
    client.get_json("r")
    fail(client)
    fail(client)
    assert client.get_json("r") == {}


def test_it_stays_open_until_the_cooldown_has_passed():
    clock = Clock()
    transport = Script(status(503), status(503), status(503), ok(b'{"back": true}'))
    client = make(transport, clock)
    for _ in range(3):
        fail(client)
    clock.now = 509.999
    fail(client, fetchkit.CircuitOpenError)
    assert transport.sent == 3
    clock.now = 510.0
    assert client.get_json("r") == {"back": True}
    assert transport.sent == 4


def test_a_successful_trial_closes_the_circuit():
    clock = Clock()
    transport = Script(status(503), status(503), status(503), ok(), status(503), status(503), ok())
    client = make(transport, clock)
    for _ in range(3):
        fail(client)
    clock.now = 520.0
    client.get_json("r")
    fail(client)
    fail(client)
    assert client.get_json("r") == {}  # two failures after closing: still closed


def test_a_failed_trial_reopens_at_once_for_another_cooldown():
    clock = Clock()
    transport = Script(status(503), status(503), status(503), TransportError("timed out"), ok())
    client = make(transport, clock)
    for _ in range(3):
        fail(client)
    clock.now = 512.0
    fail(client, TransportError)  # the trial
    fail(client, fetchkit.CircuitOpenError)
    clock.now = 521.5
    fail(client, fetchkit.CircuitOpenError)
    assert transport.sent == 4
    clock.now = 522.0
    assert client.get_json("r") == {}
    assert transport.sent == 5


def test_cached_responses_bypass_the_breaker():
    clock = Clock()
    transport = Script(ok(b'{"id": 7}'), status(503))
    client = make(transport, clock, cache=LRUCache(maxsize=8))
    assert client.get_json("users/7") == {"id": 7}
    for _ in range(3):
        fail(client)
    assert client.get_json("users/7") == {"id": 7}
    fail(client, fetchkit.CircuitOpenError)
    assert transport.sent == 4


def test_cache_hits_do_not_reset_the_streak():
    clock = Clock()
    transport = Script(ok(b'{"id": 7}'), status(503))
    client = make(transport, clock, cache=LRUCache(maxsize=8))
    client.get_json("users/7")
    fail(client)
    fail(client)
    client.get_json("users/7")  # cached
    fail(client)
    fail(client, fetchkit.CircuitOpenError)


def test_existing_behaviour_is_unchanged():
    transport = Script(status(500), ok(b'{"n": 2}'))
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=4))
    fail(client)
    assert client.get_json("r") == {"n": 2}
    assert client.get_json("r") == {"n": 2}
    assert transport.sent == 2
    assert client.url("search", {"q": "desk lamp", "page": 2, "sort": None}) == BASE + "/search?page=2&q=desk+lamp"
