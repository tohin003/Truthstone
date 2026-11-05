"""Hidden checks: a charset in Content-Type is used; without one, decoding is what it was
(UTF-8, UTF-8 with a byte-order mark, UTF-16 with a byte-order mark); errors stay DecodeErrors."""

import json

import pytest

from fetchkit.client import Client
from fetchkit.errors import DecodeError
from fetchkit.transport import Response

PAYLOAD = {"name": "José Øyvind", "city": "Malmö", "n": 3}


class Replay:
    def __init__(self, body, headers):
        self.response = Response(200, body, headers)

    def send(self, method, url, headers, timeout=None):
        return self.response


def get(body, content_type):
    headers = {} if content_type is None else {"Content-Type": content_type}
    return Client("https://internal.example/api", transport=Replay(body, headers)).get_json("x")


def encoded(encoding):
    return json.dumps(PAYLOAD, ensure_ascii=False).encode(encoding)


@pytest.mark.parametrize(
    "content_type",
    ["application/json; charset=iso-8859-1", "application/json; charset=ISO-8859-1", 'application/json;charset="iso-8859-1"'],
)
def test_the_charset_in_content_type_is_used(content_type):
    assert get(encoded("latin-1"), content_type) == PAYLOAD


def test_other_charsets():
    assert get(encoded("cp1252"), "application/json; charset=windows-1252") == PAYLOAD
    assert get(encoded("utf-8"), "application/json; charset=utf-8") == PAYLOAD


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32"])
@pytest.mark.parametrize("content_type", [None, "application/json"])
def test_without_a_charset_decoding_is_unchanged(encoding, content_type):
    assert get(encoded(encoding), content_type) == PAYLOAD


def test_an_unknown_charset_is_a_decode_error():
    with pytest.raises(DecodeError):
        get(encoded("utf-8"), "application/json; charset=no-such-charset")


def test_invalid_json_is_still_a_decode_error():
    with pytest.raises(DecodeError):
        get(b"<html>", "text/html; charset=utf-8")
    with pytest.raises(DecodeError):
        get("{\"name\": \"José\"}".encode("latin-1"), "application/json")
