"""Hidden checks: the documented rule holds; no absolute URL leaves with the client's headers."""

import json

import pytest

from fetchkit.client import Client
from fetchkit.transport import Response


class Recorder:
    def __init__(self):
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append((url, dict(headers)))
        return Response(200, json.dumps({"ok": True}).encode(), {"Content-Type": "application/json"})


@pytest.mark.parametrize(
    "target",
    [
        "https://cdn.partner.example/v2/items?cursor=c2",
        "https://elsewhere.example.com/steal",
        "http://api.example.com/v1/users",
    ],
)
def test_absolute_urls_are_refused_and_nothing_is_sent(target):
    transport = Recorder()
    client = Client("https://api.example.com/v1", transport=transport, headers={"Authorization": "Bearer t0ken"})
    with pytest.raises(ValueError):
        client.get_json(target)
    with pytest.raises(ValueError):
        client.url(target)
    assert transport.requests == []


def test_relative_paths_still_work():
    transport = Recorder()
    client = Client("https://api.example.com/v1", transport=transport, headers={"Authorization": "Bearer t0ken"})
    assert client.get_json("users/42", {"page": 2}) == {"ok": True}
    assert transport.requests == [("https://api.example.com/v1/users/42?page=2", {"Accept": "application/json", "Authorization": "Bearer t0ken"})]
