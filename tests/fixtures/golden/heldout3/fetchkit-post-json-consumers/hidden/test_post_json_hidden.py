"""post_json sends JSON through the real transport and decodes like get_json; POSTs are never
cached; transports with the documented send(method, url, headers, timeout) keep working."""

import io
import json
import urllib.error
import urllib.request

import pytest

from fetchkit import Client, ClientError, LRUCache, ServerError
from fetchkit.transport import Response, UrllibTransport

BASE = "https://api.example.com/v1"


class Raw:
    def __init__(self, status, body):
        self.status = status
        self.headers = {"Content-Type": "application/json"}
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def server(monkeypatch):
    """urllib's urlopen answered from a queue of (status, body) replies; records each request."""
    state = {"replies": [], "requests": []}

    def urlopen(request, timeout=None):
        state["requests"].append(
            {
                "method": request.get_method(),
                "url": request.full_url,
                "data": request.data,
                "headers": {name.lower(): value for name, value in request.header_items()},
                "timeout": timeout,
            }
        )
        status, body = state["replies"].pop(0)
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "error", {}, io.BytesIO(body))
        return Raw(status, body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return state


class OldStyleTransport:
    """A transport written to the documented interface: send(method, url, headers, timeout)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def send(self, method, url, headers, timeout=None):
        self.calls.append((method, url, dict(headers), timeout))
        return self.replies.pop(0)


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_post_json_sends_the_payload_as_json(server):
    server["replies"].append((201, b'{"id": "O-17"}'))
    client = Client(BASE, transport=UrllibTransport(), headers={"Authorization": "Bearer t0k3n"})
    assert client.post_json("orders", {"sku": "D-1", "quantity": 2}) == {"id": "O-17"}
    [request] = server["requests"]
    assert request["method"] == "POST"
    assert request["url"] == f"{BASE}/orders"
    assert json.loads(request["data"]) == {"sku": "D-1", "quantity": 2}
    assert request["headers"]["content-type"].split(";")[0].strip() == "application/json"
    assert request["headers"]["authorization"] == "Bearer t0k3n"
    assert request["headers"]["accept"] == "application/json"


def test_post_json_returns_none_for_an_empty_body(server):
    server["replies"].append((204, b""))
    assert Client(BASE, transport=UrllibTransport()).post_json("orders/O-17/cancel", {}) is None


@pytest.mark.parametrize("status, error", [(409, ClientError), (502, ServerError)])
def test_post_json_raises_like_get_json(server, status, error):
    server["replies"].append((status, b'{"error": "duplicate order"}'))
    with pytest.raises(error) as info:
        Client(BASE, transport=UrllibTransport()).post_json("orders", {"sku": "D-1"})
    assert info.value.status == status
    assert info.value.body == b'{"error": "duplicate order"}'


def test_post_responses_are_never_cached_and_never_read_from_the_cache(server):
    server["replies"] += [(200, b'{"v": 1}'), (201, b'{"created": 1}'), (201, b'{"created": 2}'), (200, b'{"v": 1}')]
    client = Client(BASE, transport=UrllibTransport(), cache=LRUCache(maxsize=8))
    assert client.get_json("orders") == {"v": 1}
    assert client.post_json("orders", {"sku": "D-1"}) == {"created": 1}
    assert client.post_json("orders", {"sku": "D-1"}) == {"created": 2}
    assert client.get_json("orders") == {"v": 1}
    assert [r["method"] for r in server["requests"]][:3] == ["GET", "POST", "POST"]


def test_gets_still_work_through_a_transport_with_the_documented_interface():
    transport = OldStyleTransport(Response(200, b'{"levels": []}'), Response(404, b'{"error": "nope"}'))
    client = Client(BASE, transport=transport, timeout=3.0)
    assert client.get_json("levels", params={"sku": "D-1"}) == {"levels": []}
    with pytest.raises(ClientError):
        client.get_json("missing")
    assert [(m, u, t) for m, u, _, t in transport.calls] == [
        ("GET", f"{BASE}/levels?sku=D-1", 3.0),
        ("GET", f"{BASE}/missing", 3.0),
    ]
    assert transport.calls[0][2]["Accept"] == "application/json"


def test_a_wrapping_transport_like_the_services_keeps_working(server):
    class Signing:
        def __init__(self):
            self.inner = UrllibTransport()

        def send(self, method, url, headers, timeout=None):
            return self.inner.send(method, url, {**headers, "X-Signature": "abc"}, timeout=timeout)

    server["replies"].append((200, b'{"ok": true}'))
    assert Client(BASE, transport=Signing()).get_json("ping") == {"ok": True}
    assert server["requests"][0]["headers"]["x-signature"] == "abc"
    assert server["requests"][0]["method"] == "GET"


def test_posts_are_spaced_out_like_every_other_request(server):
    server["replies"] += [(200, b"{}"), (201, b"{}")]
    clock = FakeClock()
    client = Client(BASE, transport=UrllibTransport(), min_interval=0.5, clock=clock, sleep=clock.sleep)
    client.get_json("a")
    client.post_json("b", {"x": 1})
    assert clock.sleeps == [pytest.approx(0.5)]


def test_get_requests_are_unchanged(server):
    server["replies"].append((200, b'{"id": 42}'))
    client = Client(BASE, transport=UrllibTransport())
    assert client.get_json("users/42", params={"fields": "name", "x": None}) == {"id": 42}
    [request] = server["requests"]
    assert request["method"] == "GET"
    assert request["url"] == f"{BASE}/users/42?fields=name"
    assert request["data"] is None
