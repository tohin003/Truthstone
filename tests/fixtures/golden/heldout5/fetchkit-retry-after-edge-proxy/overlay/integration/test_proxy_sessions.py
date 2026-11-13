"""Replays sessions recorded from the API edge proxy through Client (run by `make check`)."""

import json
from pathlib import Path

import pytest

import fetchkit
from fetchkit.client import Client
from fetchkit.transport import Response

SESSIONS = sorted((Path(__file__).parent / "sessions").glob("*.json"))
BASE = "https://api.example.com/v1"


class Replay:
    """A transport that answers with the recorded exchanges, in order."""

    def __init__(self, exchanges):
        self.exchanges = list(exchanges)
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append((method, url))
        if not self.exchanges:
            raise AssertionError(f"the recording has no more exchanges for {method} {url}")
        step = self.exchanges.pop(0)
        return Response(step["status"], json.dumps(step["body"]).encode(), dict(step["headers"]))


class Clock:
    def __init__(self):
        self.now = 5000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.parametrize("session", SESSIONS, ids=lambda path: path.stem)
def test_recorded_session(session):
    recording = json.loads(session.read_text(encoding="utf-8"))
    transport, clock = Replay(recording["exchanges"]), Clock()
    client = Client(BASE, transport=transport, clock=clock, sleep=clock.sleep)
    expect = recording["expect"]
    if "error" in expect:
        with pytest.raises(getattr(fetchkit, expect["error"])) as info:
            client.get_json(recording["path"])
        assert info.value.status == expect["status"]
    else:
        assert client.get_json(recording["path"]) == expect["result"]
    assert len(transport.requests) == expect["requests"]
    assert clock.sleeps == expect["sleeps"]
