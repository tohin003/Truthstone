"""Circuit breaker (README, "Circuit breaker"). Uses pytest-mock: pip install -e '.[test]'."""

import json

import pytest

from fetchkit import Client, LRUCache, errors
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


def ok(payload=None):
    return Response(200, json.dumps(payload or {}).encode(), {"Content-Type": "application/json"})


def status(code):
    return Response(code, b"", {"Content-Type": "application/json"})


@pytest.fixture
def clock(mocker):
    return mocker.Mock(return_value=1000.0)


@pytest.fixture
def transport(mocker):
    return mocker.Mock()


def breaker_client(transport, clock, **options):
    return Client(BASE, transport=transport, clock=clock, failure_threshold=3, cooldown=30.0, **options)


def test_opens_after_three_consecutive_failures(transport, clock):
    transport.send.side_effect = [status(503), errors.TransportError("refused"), status(500)]
    client = breaker_client(transport, clock)
    for expected in (errors.ServerError, errors.TransportError, errors.ServerError):
        with pytest.raises(expected):
            client.get_json("reports")
    with pytest.raises(errors.CircuitOpenError):
        client.get_json("reports")
    assert transport.send.call_count == 3


def test_client_errors_are_not_failures(transport, clock):
    transport.send.side_effect = [status(503), status(503), status(404), status(503), status(503), ok()]
    client = breaker_client(transport, clock)
    for _ in range(5):
        with pytest.raises(errors.HTTPError):
            client.get_json("reports")
    assert client.get_json("reports") == {}


def test_a_body_that_is_not_json_still_resets_the_count(transport, clock):
    html = Response(200, b"<html>maintenance</html>", {"Content-Type": "text/html"})
    transport.send.side_effect = [status(503), status(503), html, status(503), status(503), ok()]
    client = breaker_client(transport, clock)
    for expected in (errors.ServerError, errors.ServerError, errors.DecodeError, errors.ServerError, errors.ServerError):
        with pytest.raises(expected):
            client.get_json("reports")
    assert client.get_json("reports") == {}


def test_a_success_resets_the_count(transport, clock):
    transport.send.side_effect = [status(503), status(503), ok(), status(503), status(503), ok()]
    client = breaker_client(transport, clock)
    for step in range(6):
        if step in (2, 5):
            client.get_json("reports")
        else:
            with pytest.raises(errors.ServerError):
                client.get_json("reports")


def test_a_trial_after_the_cooldown_closes_the_circuit(transport, clock):
    transport.send.side_effect = [status(503)] * 3 + [ok({"n": 1}), status(503), ok({"n": 2})]
    client = breaker_client(transport, clock)
    for _ in range(3):
        with pytest.raises(errors.ServerError):
            client.get_json("reports")
    clock.return_value = 1029.9
    with pytest.raises(errors.CircuitOpenError):
        client.get_json("reports")
    clock.return_value = 1030.0
    assert client.get_json("reports") == {"n": 1}
    with pytest.raises(errors.ServerError):
        client.get_json("reports")
    assert client.get_json("reports") == {"n": 2}


def test_a_failed_trial_reopens_the_circuit_at_once(transport, clock):
    transport.send.side_effect = [status(503)] * 4 + [ok()]
    client = breaker_client(transport, clock)
    for _ in range(3):
        with pytest.raises(errors.ServerError):
            client.get_json("reports")
    clock.return_value = 1031.0
    with pytest.raises(errors.ServerError):
        client.get_json("reports")  # the trial
    with pytest.raises(errors.CircuitOpenError):
        client.get_json("reports")
    clock.return_value = 1060.5
    with pytest.raises(errors.CircuitOpenError):
        client.get_json("reports")
    clock.return_value = 1061.0
    assert client.get_json("reports") == {}


def test_cached_responses_are_served_while_the_circuit_is_open(transport, clock):
    transport.send.side_effect = [ok({"id": 7})] + [status(503)] * 3
    client = breaker_client(transport, clock, cache=LRUCache(maxsize=8))
    assert client.get_json("users/7") == {"id": 7}
    for _ in range(3):
        with pytest.raises(errors.ServerError):
            client.get_json("reports")
    assert client.get_json("users/7") == {"id": 7}
    with pytest.raises(errors.CircuitOpenError):
        client.get_json("reports")
