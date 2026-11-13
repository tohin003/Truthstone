import json

import pytest

from fetchkit.client import Client
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Recorder:
    def __init__(self):
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append({"url": url, "headers": dict(headers)})
        return Response(200, json.dumps({"ok": True}).encode(), {})


@pytest.mark.parametrize(
    "path",
    [
        "https://cdn.example.net/exports/2026-11-12.json",
        "https://elsewhere.example.com/steal",
        "http://api.example.com/v1/users",
    ],
)
def test_absolute_urls_are_refused_and_nothing_is_sent(path):
    transport = Recorder()
    client = Client(BASE, transport=transport, headers={"Authorization": "Bearer t0k3n"})
    with pytest.raises(ValueError):
        client.get_json(path)
    with pytest.raises(ValueError):
        client.url(path)
    assert transport.requests == []


def test_relative_paths_still_work():
    transport = Recorder()
    client = Client(BASE, transport=transport, headers={"Authorization": "Bearer t0k3n"})
    assert client.get_json("exports/2026-11-12") == {"ok": True}
    assert transport.requests == [
        {
            "url": f"{BASE}/exports/2026-11-12",
            "headers": {"Accept": "application/json", "Authorization": "Bearer t0k3n"},
        }
    ]
