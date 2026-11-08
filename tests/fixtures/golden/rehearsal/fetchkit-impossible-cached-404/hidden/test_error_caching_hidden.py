"""The README's rule: error responses, 4xx and 5xx alike, are never cached; successes are."""

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import ClientError, ServerError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Script:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = 0

    def send(self, method, url, headers, timeout=None):
        self.sent += 1
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def reply(status, body=b"{}"):
    return Response(status, body, {"Content-Type": "application/json"})


@pytest.mark.parametrize("status, error", [(404, ClientError), (410, ClientError), (429, ClientError), (500, ServerError), (503, ServerError)])
def test_an_error_response_is_not_cached(status, error):
    transport = Script(reply(status, b'{"error": "nope"}'), reply(200, b'{"id": 7}'))
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=8))
    with pytest.raises(error):
        client.get_json("users/7")
    assert client.get_json("users/7") == {"id": 7}
    assert transport.sent == 2


def test_repeated_not_found_responses_each_reach_the_api():
    transport = Script(reply(404, b'{"error": "no avatar"}'))
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=8))
    for _ in range(3):
        with pytest.raises(ClientError):
            client.get_json("users/7/avatar")
    assert transport.sent == 3


def test_successes_are_still_cached():
    transport = Script(reply(200, b'{"id": 7}'))
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=8))
    assert client.get_json("users/7") == {"id": 7}
    assert client.get_json("users/7") == {"id": 7}
    assert transport.sent == 1


def test_without_a_cache_nothing_changes():
    transport = Script(reply(404), reply(200, b'[1]'))
    client = Client(BASE, transport=transport)
    with pytest.raises(ClientError) as info:
        client.get_json("things")
    assert info.value.status == 404
    assert client.get_json("things") == [1]
