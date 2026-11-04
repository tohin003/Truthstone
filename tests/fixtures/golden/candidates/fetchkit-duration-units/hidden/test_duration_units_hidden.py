"""Durations in milliseconds: same behaviour, new units, old names gone, the shipped registry intact."""

import urllib.request

import pytest

from fetchkit.client import Client
from fetchkit.registry import client_for
from fetchkit.transport import Response, UrllibTransport

BASE = "https://api.example.com/v1"


class Recorder:
    def __init__(self):
        self.timeouts = []

    def send(self, method, url, headers, timeout=None):
        self.timeouts.append(timeout)
        return Response(200, b"{}", {"Content-Type": "application/json"})


class Clock:
    def __init__(self):
        self.now = 500.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_timeout_ms_reaches_the_transport_in_seconds():
    transport = Recorder()
    client = Client(BASE, transport=transport, timeout_ms=2500)
    client.get_json("a")
    client.get_json("b", timeout_ms=500)
    assert transport.timeouts == [pytest.approx(2.5), pytest.approx(0.5)]


def test_the_default_timeout_is_still_ten_seconds():
    transport = Recorder()
    Client(BASE, transport=transport).get_json("a")
    assert transport.timeouts == [pytest.approx(10.0)]


def test_urllib_transport_still_defaults_to_ten_seconds(monkeypatch):
    seen = []

    class Raw:
        status = 204
        headers = {}

        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        seen.append(timeout)
        return Raw()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    UrllibTransport().send("GET", BASE + "/health", {})
    assert seen == [pytest.approx(10.0)]


def test_min_interval_ms_spaces_requests_out():
    transport, clock = Recorder(), Clock()
    client = Client(BASE, transport=transport, min_interval_ms=500, clock=clock, sleep=clock.sleep)
    client.get_json("a")
    clock.now += 0.2
    client.get_json("b")
    client.get_json("c")
    assert clock.sleeps == pytest.approx([0.3, 0.5])


@pytest.mark.parametrize("old", [{"timeout": 2.5}, {"min_interval": 0.5}])
def test_the_old_client_options_are_gone(old):
    with pytest.raises(TypeError):
        Client(BASE, transport=Recorder(), **old)


def test_the_old_per_call_timeout_is_gone():
    client = Client(BASE, transport=Recorder())
    with pytest.raises(TypeError):
        client.get_json("a", timeout=1)


@pytest.mark.parametrize(
    ("service", "base_url", "seconds", "spacing"),
    [
        ("billing", "https://billing.internal.example/v2", 5.0, 0.2),
        ("inventory", "https://inventory.internal.example/v1", 2.5, 0.0),
        ("search", "https://search.internal.example/v3", 30.0, 1.0),
        ("ledger", "https://ledger.internal.example/v1", 10.0, 0.0),
    ],
)
def test_every_shipped_service_keeps_its_timings(service, base_url, seconds, spacing):
    transport, clock = Recorder(), Clock()
    client = client_for(service, transport=transport, clock=clock, sleep=clock.sleep)
    assert client.url("x") == base_url + "/x"
    client.get_json("a")
    client.get_json("b")
    assert transport.timeouts == [pytest.approx(seconds)] * 2
    assert clock.sleeps == ([pytest.approx(spacing)] if spacing else [])


def test_a_registry_file_takes_the_millisecond_keys(tmp_path):
    path = tmp_path / "services.toml"
    path.write_text('[demo]\nbase_url = "https://demo.example/v1"\ntimeout_ms = 1500\nmin_interval_ms = 250\n')
    transport, clock = Recorder(), Clock()
    client = client_for("demo", path=path, transport=transport, clock=clock, sleep=clock.sleep)
    client.get_json("a")
    client.get_json("b")
    assert transport.timeouts == [pytest.approx(1.5)] * 2
    assert clock.sleeps == [pytest.approx(0.25)]
