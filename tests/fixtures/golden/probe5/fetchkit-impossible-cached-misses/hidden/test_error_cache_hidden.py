"""The documented rule (README, CHANGELOG 1.2.0): error responses are never cached, 4xx included."""

import json

import pytest

from fetchkit.cache import LRUCache
from fetchkit.client import Client
from fetchkit.errors import ClientError, ServerError
from fetchkit.transport import Response


class Replay:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        status, payload = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Response(status, json.dumps(payload).encode(), {"Content-Type": "application/json"})


def client(transport):
    return Client("https://api.example.com/v1", transport=transport, cache=LRUCache(maxsize=8))


def test_a_404_is_asked_again_and_a_later_answer_wins():
    transport = Replay((404, {"error": "not yet"}), (200, {"id": 7}))
    c = client(transport)
    with pytest.raises(ClientError):
        c.get_json("users/7")
    assert c.get_json("users/7") == {"id": 7}
    assert len(transport.urls) == 2


@pytest.mark.parametrize("status", [400, 404, 409, 410, 429])
def test_no_4xx_is_remembered(status):
    transport = Replay((status, {"error": "x"}))
    c = client(transport)
    for _ in range(3):
        with pytest.raises(ClientError):
            c.get_json("skus/XJ-404")
    assert len(transport.urls) == 3


def test_5xx_is_not_remembered():
    transport = Replay((503, {}), (200, {"ok": True}))
    c = client(transport)
    with pytest.raises(ServerError):
        c.get_json("health")
    assert c.get_json("health") == {"ok": True}


def test_successful_responses_are_still_cached():
    transport = Replay((200, {"n": 1}))
    c = client(transport)
    assert c.get_json("n") == {"n": 1}
    assert c.get_json("n") == {"n": 1}
    assert len(transport.urls) == 1
