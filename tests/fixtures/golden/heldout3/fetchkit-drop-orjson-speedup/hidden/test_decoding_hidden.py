"""After the clean-up the client decodes exactly as before, with the standard library."""

import json

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import ClientError, DecodeError, ServerError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Replies:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return self.responses.pop(0)


def client(*responses, **options):
    return Client(BASE, transport=Replies(*responses), **options)


def ok(payload):
    return Response(200, json.dumps(payload).encode(), {})


def test_objects_lists_and_scalars_decode():
    assert client(ok({"id": 42, "tags": ["a", "b"]})).get_json("users/42") == {"id": 42, "tags": ["a", "b"]}
    assert client(ok([1, 2.5, None, True])).get_json("list") == [1, 2.5, None, True]
    assert client(Response(200, b'"text"', {})).get_json("scalar") == "text"


def test_non_ascii_and_big_numbers_survive():
    body = '{"name": "Zoë", "big": 12345678901234567890, "price": 0.1}'.encode()
    assert client(Response(200, body, {})).get_json("x") == {"name": "Zoë", "big": 12345678901234567890, "price": 0.1}


@pytest.mark.parametrize("body", [b"<html>oops</html>", b'{"a": ', b"\xff\xfe\x00", b"NaN-ish"])
def test_bodies_that_are_not_json_raise_decode_error(body):
    with pytest.raises(DecodeError):
        client(Response(200, body, {})).get_json("x")


def test_empty_bodies_are_none():
    assert client(Response(204, b"", {})).get_json("ping") is None


def test_error_statuses_still_raise_before_decoding():
    with pytest.raises(ClientError):
        client(Response(404, b"not json at all", {})).get_json("missing")
    with pytest.raises(ServerError):
        client(Response(503, b"", {})).get_json("down")


def test_the_cache_still_serves_decoded_bodies():
    replies = Replies(ok({"n": 1}))
    c = Client(BASE, transport=replies, cache=LRUCache(maxsize=4))
    assert c.get_json("n") == {"n": 1}
    assert c.get_json("n") == {"n": 1}
    assert len(replies.urls) == 1
