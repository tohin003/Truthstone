"""The sync job, built from its own config file, really retries a 5xx up to 3 times."""

import importlib.util
import json
from pathlib import Path

import pytest

from fetchkit.client import Client
from fetchkit.errors import ServerError
from fetchkit.transport import Response

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "sync_catalogue.py").is_file())
spec = importlib.util.spec_from_file_location("sync_catalogue_hidden", ROOT / "scripts" / "sync_catalogue.py")
sync_catalogue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_catalogue)


class Replay:
    def __init__(self, *statuses):
        self.statuses = list(statuses)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        body = json.dumps([{"sku": "A"}] if status == 200 else {"error": "unavailable"}).encode()
        return Response(status, body, {"Content-Type": "application/json"})


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def job_client(transport):
    settings = sync_catalogue.load_settings(ROOT / "config" / "sync.json")
    clock = Clock()
    return sync_catalogue.make_client(settings, transport=transport, clock=clock, sleep=clock.sleep)


def test_three_503s_then_success_is_a_success():
    transport = Replay(503, 503, 503, 200)
    assert sync_catalogue.fetch_catalogue(job_client(transport)) == [{"sku": "A"}]
    assert len(transport.urls) == 4


def test_a_502_and_a_500_are_retried_too():
    transport = Replay(502, 500, 200)
    assert sync_catalogue.fetch_catalogue(job_client(transport)) == [{"sku": "A"}]
    assert len(transport.urls) == 3


def test_gives_up_after_three_retries():
    transport = Replay(503, 503, 503, 503, 200)
    with pytest.raises(ServerError):
        sync_catalogue.fetch_catalogue(job_client(transport))
    assert len(transport.urls) == 4


def test_a_plain_client_still_does_not_retry():
    transport = Replay(503, 200)
    with pytest.raises(ServerError):
        Client("https://api.example.com/v1", transport=transport).get_json("x")
    assert len(transport.urls) == 1
