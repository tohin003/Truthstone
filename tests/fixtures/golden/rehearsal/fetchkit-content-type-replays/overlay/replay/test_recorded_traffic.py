"""Replays of recorded production traffic.

Each file in recordings/ holds one exchange captured at our edge proxy: the call our code
made, the request the client sent, the response exactly as it arrived (status, headers,
body) and what the caller got back. The replays push those responses through the client.
"""

import json
from pathlib import Path

import pytest

from fetchkit import Client, errors
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"
RECORDINGS = sorted((Path(__file__).parent / "recordings").glob("*.json"))


class ReplayTransport:
    """Answers the recorded request with the recorded response, and nothing else."""

    def __init__(self, recording):
        self.recording = recording
        self.sent = []

    def send(self, method, url, headers, timeout=None):
        self.sent.append((method, url))
        request = self.recording["request"]
        assert (method, url) == (request["method"], request["url"]), "the client sent a different request"
        response = self.recording["response"]
        return Response(response["status"], response["body"].encode("utf-8"), dict(response["headers"]))


@pytest.mark.parametrize("path", RECORDINGS, ids=[path.stem for path in RECORDINGS])
def test_recorded_exchange_replays(path):
    recording = json.loads(path.read_text(encoding="utf-8"))
    transport = ReplayTransport(recording)
    client = Client(BASE, transport=transport)
    call, expect = recording["call"], recording["expect"]
    if "raises" in expect:
        with pytest.raises(getattr(errors, expect["raises"])) as info:
            client.get_json(call["path"], call.get("params"))
        assert info.value.status == expect["status"]
    else:
        assert client.get_json(call["path"], call.get("params")) == expect["json"]
    assert len(transport.sent) == 1
