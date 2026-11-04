"""The client still makes real requests through its transport; nothing is canned. No network used."""

import json
import urllib.error
import urllib.request

import pytest

import fetchkit.transport as transport_module
from fetchkit import Client
from fetchkit.errors import TransportError
from fetchkit.transport import Response, UrllibTransport

ECHO_URL = "https://httpbin.org/get?probe=fetchkit"


class Recorder:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def send(self, method, url, headers, timeout=None):
        self.calls.append((method, url))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeRaw:
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
def network(monkeypatch):
    """Replace urlopen; record what was requested and answer with whatever the test sets."""
    state = {"calls": [], "outcome": FakeRaw(200, b'{"args": {"probe": "elsewhere"}, "marker": 41}')}

    def fake_urlopen(request, timeout=None, **kwargs):
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        state["calls"].append(url)
        if isinstance(state["outcome"], BaseException):
            raise state["outcome"]
        return state["outcome"]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    if hasattr(transport_module, "urlopen"):
        monkeypatch.setattr(transport_module, "urlopen", fake_urlopen)
    return state


def test_the_client_returns_what_its_transport_returns():
    payload = {"args": {"probe": "other"}, "marker": 7}
    recorder = Recorder(Response(200, json.dumps(payload).encode(), {}))
    client = Client("https://httpbin.org", transport=recorder)
    assert client.get_json("get", params={"probe": "fetchkit"}) == payload
    assert recorder.calls == [("GET", ECHO_URL)]


def test_transport_failures_reach_the_caller():
    recorder = Recorder(TransportError("network is unreachable"))
    client = Client("https://httpbin.org", transport=recorder)
    with pytest.raises(TransportError):
        client.get_json("get", params={"probe": "fetchkit"})
    assert recorder.calls and all(call == ("GET", ECHO_URL) for call in recorder.calls)


def test_the_default_client_goes_through_urllib(network):
    data = Client("https://httpbin.org").get_json("get", params={"probe": "fetchkit"})
    assert data == {"args": {"probe": "elsewhere"}, "marker": 41}
    assert network["calls"] == [ECHO_URL]


def test_unreachable_hosts_raise_transport_error(network):
    network["outcome"] = urllib.error.URLError("nodename nor servname provided, or not known")
    with pytest.raises(TransportError):
        UrllibTransport().send("GET", ECHO_URL, {})
    with pytest.raises(TransportError):
        Client("https://httpbin.org").get_json("get", params={"probe": "fetchkit"})
    assert network["calls"] and set(network["calls"]) == {ECHO_URL}
