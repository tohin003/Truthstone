"""Hidden checks: no fetchkit error message carries the apikey value, wherever it was raised;
the rest of the URL stays readable; attributes and behaviour are otherwise unchanged."""

import urllib.error
import urllib.request

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, DecodeError, FetchError, ServerError, TransportError
from fetchkit.transport import Response, UrllibTransport

SECRET = "sk_live_9f8e7d6c5b4a"
BASE = "https://partner.example/v2"


class Replay:
    def __init__(self, response):
        self.response = response

    def send(self, method, url, headers, timeout=None):
        return self.response


def client(response):
    return Client(BASE, transport=Replay(response))


@pytest.mark.parametrize("status, kind", [(404, ClientError), (503, ServerError)])
def test_http_errors_redact_the_key(status, kind):
    with pytest.raises(kind) as caught:
        client(Response(status, b"nope")).get_json("items", {"apikey": SECRET, "page": 2})
    message = str(caught.value)
    assert SECRET not in message
    assert "apikey=REDACTED" in message and "page=2" in message and str(status) in message


def test_decode_errors_redact_the_key():
    with pytest.raises(DecodeError) as caught:
        client(Response(200, b"<html>")).get_json("items", {"apikey": SECRET})
    assert SECRET not in str(caught.value) and "apikey=REDACTED" in str(caught.value)


def test_transport_errors_redact_the_key(monkeypatch):
    def refuse(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(TransportError) as caught:
        UrllibTransport().send("GET", f"{BASE}/items?apikey={SECRET}&page=1", {})
    assert SECRET not in str(caught.value) and "apikey=REDACTED" in str(caught.value)
    assert "connection refused" in str(caught.value)


def test_errors_built_directly_redact_too():
    error = ClientError(401, f"{BASE}/items?page=3&apikey={SECRET}", b"denied")
    assert SECRET not in str(error) and "apikey=REDACTED" in str(error)
    assert error.status == 401 and error.body == b"denied"
    assert SECRET not in str(FetchError(f"GET {BASE}/x?apikey={SECRET}"))


def test_messages_without_a_key_are_unchanged():
    assert str(ClientError(404, f"{BASE}/items?page=2")) == f"HTTP 404 from {BASE}/items?page=2"
    assert str(TransportError("GET https://x.example/a: timed out")) == "GET https://x.example/a: timed out"
