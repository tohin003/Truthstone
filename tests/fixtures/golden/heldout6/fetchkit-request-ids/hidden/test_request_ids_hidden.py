"""Request ids as requested: a header on every request, the caller's id when given, and the id on
every error the client raises (HTTP errors and requests that got no response)."""

import json
import re

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import ClientError, FetchError, ServerError, TransportError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Script:
    """Replays scripted outcomes in order (the last one repeats) and records each request."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append({"method": method, "url": url, "headers": dict(headers)})
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, BaseException):
            raise step
        return step


def ok(payload=None):
    return Response(200, json.dumps(payload if payload is not None else {}).encode(), {})


def header(request):
    return request["headers"]["X-Request-Id"]


def test_every_request_gets_a_fresh_uuid4_hex_id():
    transport = Script(ok())
    client = Client(BASE, transport=transport)
    client.get_json("a")
    client.get_json("b")
    ids = [header(r) for r in transport.requests]
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in ids)
    assert ids[0] != ids[1]


def test_the_callers_id_is_used_when_given():
    transport = Script(ok())
    Client(BASE, transport=transport).get_json("orders/7", request_id="trace-7781")
    assert header(transport.requests[0]) == "trace-7781"


def test_other_headers_are_still_sent():
    transport = Script(ok())
    Client(BASE, transport=transport, headers={"Authorization": "Bearer t"}).get_json("me")
    headers = transport.requests[0]["headers"]
    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == "Bearer t"


@pytest.mark.parametrize("status, error", [(404, ClientError), (429, ClientError), (503, ServerError)])
def test_http_errors_carry_the_id_they_were_sent_with(status, error):
    transport = Script(Response(status, b'{"error": "x"}', {}))
    client = Client(BASE, transport=transport)
    with pytest.raises(error) as info:
        client.get_json("things")
    assert info.value.request_id == header(transport.requests[0])
    assert info.value.status == status


def test_http_errors_carry_the_callers_id():
    transport = Script(Response(500, b"", {}))
    with pytest.raises(ServerError) as info:
        Client(BASE, transport=transport).get_json("things", request_id="job-42")
    assert info.value.request_id == "job-42"


def test_transport_errors_carry_the_id_too():
    transport = Script(TransportError("connection refused"))
    client = Client(BASE, transport=transport)
    with pytest.raises(TransportError) as info:
        client.get_json("things")
    sent = header(transport.requests[0])
    assert info.value.request_id == sent
    assert sent in str(info.value)
    assert isinstance(info.value, FetchError)


def test_transport_errors_carry_the_callers_id():
    transport = Script(TransportError("timed out"))
    with pytest.raises(TransportError) as info:
        Client(BASE, transport=transport).get_json("slow", request_id="nightly-sync-3")
    assert info.value.request_id == "nightly-sync-3"
    assert "nightly-sync-3" in str(info.value)


def test_caching_and_decoding_are_unchanged():
    transport = Script(ok({"n": 1}))
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=4))
    assert client.get_json("n") == {"n": 1}
    assert client.get_json("n") == {"n": 1}
    assert len(transport.requests) == 1
