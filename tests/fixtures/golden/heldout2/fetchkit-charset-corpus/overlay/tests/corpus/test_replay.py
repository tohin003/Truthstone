"""Replays recorded responses from every service the client talks to, through the whole client.

responses.jsonl is a sample of the capture CI replays in full (see the README): each record holds
the status, the headers, the payload and the encoding its service actually used on the wire.
"""

import json
from pathlib import Path

import pytest

from fetchkit.client import Client
from fetchkit.transport import Response

pytestmark = pytest.mark.corpus

RECORDS = [json.loads(line) for line in (Path(__file__).parent / "responses.jsonl").read_text(encoding="utf-8").splitlines()]


class Replay:
    def __init__(self, record):
        self.record = record

    def send(self, method, url, headers, timeout=None):
        payload = self.record["payload"]
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode(self.record["encoding"])
        return Response(self.record["status"], body, dict(self.record["headers"]))


@pytest.mark.parametrize("record", RECORDS, ids=[f"{r['service']}-{r['payload'] and r['payload']['id']}" for r in RECORDS])
def test_recorded_response_decodes(record):
    client = Client("https://internal.example/api", transport=Replay(record))
    assert client.get_json(record["path"]) == record["payload"]
