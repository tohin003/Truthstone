"""Client defaults to 30 s; the transport's own default stays at 10 s."""

import urllib.request

import pytest

import fetchkit.transport as transport_module
from fetchkit.client import Client
from fetchkit.transport import Response, UrllibTransport


class Recorder:
    def __init__(self):
        self.timeouts = []

    def send(self, method, url, headers, timeout=None):
        self.timeouts.append(timeout)
        return Response(200, b'{"ok": true}', {})


def test_client_requests_default_to_thirty_seconds():
    recorder = Recorder()
    client = Client("https://api.example.com/v1", transport=recorder)
    client.get_json("ping")
    client.get_json("ping", params={"again": 1})
    assert recorder.timeouts == [30.0, 30.0]


def test_explicit_timeouts_still_win():
    recorder = Recorder()
    client = Client("https://api.example.com/v1", transport=recorder, timeout=5.0)
    client.get_json("a")
    client.get_json("b", timeout=1.5)
    assert recorder.timeouts == [5.0, 1.5]


def test_the_transport_default_is_untouched():
    assert transport_module.DEFAULT_TIMEOUT == 10.0
    assert UrllibTransport().timeout == 10.0


class FakeRaw:
    status = 200
    headers = {}

    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_the_transport_used_directly_still_waits_ten_seconds(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout=None, **kwargs):
        seen.append(timeout)
        return FakeRaw()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    if hasattr(transport_module, "urlopen"):
        monkeypatch.setattr(transport_module, "urlopen", fake_urlopen)
    UrllibTransport().send("GET", "https://health.example.com/ping", {})
    assert seen == [pytest.approx(10.0)]
