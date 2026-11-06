"""fetchkit asks for gzip and decodes gzip-encoded responses, errors included, through the real
transport, whatever the spelling of the header names; uncompressed responses work as before."""

import gzip
import io
import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

from fetchkit import Client, ClientError, LRUCache, ServerError
from fetchkit.transport import UrllibTransport

BASE = "https://api.example.com/v1"
PAYLOAD = {"items": [{"order_id": f"A-{n}", "total_cents": n * 125} for n in range(40)], "next": None}


def headers_of(pairs):
    message = Message()
    for name, value in pairs.items():
        message[name] = value
    return message


class Raw:
    """What urlopen returns for a success."""

    def __init__(self, status, body, headers):
        self.status = status
        self.headers = headers_of(headers)
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def server(monkeypatch):
    """urllib's urlopen answered from a queue of (status, body, headers) replies."""
    state = {"replies": [], "requests": []}

    def urlopen(request, timeout=None):
        state["requests"].append({name.lower(): value for name, value in request.header_items()})
        status, body, headers = state["replies"].pop(0)
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "error", headers_of(headers), io.BytesIO(body))
        return Raw(status, body, headers)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return state


def client(**options):
    return Client(BASE, transport=UrllibTransport(), **options)


def gz(payload):
    return gzip.compress(json.dumps(payload).encode(), mtime=0)


def test_requests_accept_gzip(server):
    server["replies"].append((200, b"{}", {"content-type": "application/json"}))
    client().get_json("orders")
    assert "gzip" in server["requests"][0].get("accept-encoding", "").lower()


@pytest.mark.parametrize("name", ["Content-Encoding", "content-encoding", "CONTENT-ENCODING"])
def test_gzip_bodies_are_decoded_whatever_the_header_spelling(server, name):
    server["replies"].append((200, gz(PAYLOAD), {"content-type": "application/json", name: "gzip"}))
    assert client().get_json("orders", params={"status": "open"}) == PAYLOAD


def test_gateway_style_response_is_decoded(server):
    server["replies"].append(
        (
            200,
            gz({"order_id": "A-1043", "status": "open"}),
            {
                "date": "Wed, 14 Oct 2026 09:12:45 GMT",
                "content-type": "application/json",
                "server": "envoy",
                "content-encoding": "gzip",
                "vary": "accept-encoding",
            },
        )
    )
    assert client().get_json("orders/A-1043") == {"order_id": "A-1043", "status": "open"}


@pytest.mark.parametrize("status, error", [(404, ClientError), (409, ClientError), (503, ServerError)])
def test_error_bodies_are_decoded_too(server, status, error):
    body = {"error": "no such order", "order_id": "A-0000"}
    server["replies"].append((status, gz(body), {"content-type": "application/json", "content-encoding": "gzip"}))
    with pytest.raises(error) as info:
        client().get_json("orders/A-0000")
    assert info.value.status == status
    assert json.loads(info.value.body) == body


def test_uncompressed_responses_work_as_before(server):
    server["replies"] += [
        (200, json.dumps(PAYLOAD).encode(), {"content-type": "application/json"}),
        (200, b'{"ok": true}', {"Content-Type": "application/json"}),
        (204, b"", {"server": "envoy"}),
    ]
    c = client()
    assert c.get_json("orders") == PAYLOAD
    assert c.get_json("ping") == {"ok": True}
    assert c.get_json("health") is None


def test_uncompressed_error_bodies_are_unchanged(server):
    server["replies"].append((404, b'{"error": "gone"}', {"content-type": "application/json"}))
    with pytest.raises(ClientError) as info:
        client().get_json("orders/A-1")
    assert info.value.body == b'{"error": "gone"}'


def test_cached_responses_are_served_decoded(server):
    server["replies"].append((200, gz(PAYLOAD), {"content-encoding": "gzip"}))
    c = client(cache=LRUCache(maxsize=4))
    assert c.get_json("orders") == PAYLOAD
    assert c.get_json("orders") == PAYLOAD
    assert len(server["requests"]) == 1


def test_other_request_headers_are_still_sent(server):
    server["replies"].append((200, b"{}", {}))
    client(headers={"Authorization": "Bearer t0k3n"}).get_json("me")
    sent = server["requests"][0]
    assert sent["accept"] == "application/json"
    assert sent["authorization"] == "Bearer t0k3n"
