"""Requests that do not set a timeout wait 15 seconds: through Client, the transport and the health checks."""

import importlib.util
import urllib.request
from pathlib import Path

import pytest

from fetchkit.client import Client
from fetchkit.transport import Response, UrllibTransport

ROOT = Path(__file__).resolve().parents[2]


class Raw:
    status = 200
    headers = {}

    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def urlopen_timeouts(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(timeout)
        return Raw()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


class Recorder:
    def __init__(self):
        self.timeouts = []

    def send(self, method, url, headers, timeout=None):
        self.timeouts.append(timeout)
        return Response(200, b"{}", {})


def test_client_default_timeout_is_15_seconds():
    transport = Recorder()
    Client("https://api.example.com/v1", transport=transport).get_json("users/1")
    assert transport.timeouts == [15.0]


def test_client_over_the_default_transport_waits_15_seconds(urlopen_timeouts):
    Client("https://api.example.com/v1").get_json("users/1")
    assert urlopen_timeouts == [15.0]


def test_transport_default_timeout_is_15_seconds(urlopen_timeouts):
    UrllibTransport().send("GET", "https://api.example.com/health", {})
    assert urlopen_timeouts == [15.0]


def test_health_checks_wait_15_seconds(urlopen_timeouts):
    spec = importlib.util.spec_from_file_location("healthcheck_under_test", ROOT / "scripts" / "healthcheck.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = module.check(module.UPSTREAMS)
    assert all(results.values())
    assert urlopen_timeouts == [15.0] * len(module.UPSTREAMS)


def test_explicit_timeouts_still_win(urlopen_timeouts):
    transport = Recorder()
    client = Client("https://api.example.com/v1", transport=transport, timeout=3.0)
    client.get_json("a")
    client.get_json("b", timeout=0.5)
    assert transport.timeouts == [3.0, 0.5]
    UrllibTransport(timeout=4.0).send("GET", "https://api.example.com/x", {})
    UrllibTransport().send("GET", "https://api.example.com/x", {}, timeout=2.0)
    assert urlopen_timeouts == [4.0, 2.0]
