"""Successful responses must be JSON (application/json, parameters allowed) or empty; header names
are matched the way HTTP matches them, and error statuses keep their own errors."""

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import ClientError, DecodeError, ServerError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"
MAINTENANCE = b"<!doctype html><html><body><h1>Back soon</h1></body></html>"


class OneReply:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = 0

    def send(self, method, url, headers, timeout=None):
        self.sent += 1
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def get(response, path="items/1"):
    return Client(BASE, transport=OneReply(response)).get_json(path)


def test_an_html_page_with_200_raises_decode_error_naming_the_type():
    with pytest.raises(DecodeError) as info:
        get(Response(200, MAINTENANCE, {"Content-Type": "text/html; charset=utf-8"}))
    assert "text/html" in str(info.value)


def test_other_non_json_types_raise_too():
    with pytest.raises(DecodeError) as info:
        get(Response(200, b"id,name\n1,Ada\n", {"Content-Type": "text/csv"}))
    assert "text/csv" in str(info.value)


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=utf-8", "application/json;charset=UTF-8"],
)
def test_json_responses_still_decode(content_type):
    assert get(Response(200, b'{"id": 1, "ok": true}', {"Content-Type": content_type})) == {"id": 1, "ok": True}


@pytest.mark.parametrize("name", ["content-type", "CONTENT-TYPE", "Content-type"])
def test_header_names_match_in_any_case(name):
    assert get(Response(200, b'{"id": 2}', {name: "application/json; charset=utf-8"})) == {"id": 2}
    with pytest.raises(DecodeError) as info:
        get(Response(200, MAINTENANCE, {name: "text/html"}))
    assert "text/html" in str(info.value)


def test_a_lower_case_header_among_others_as_the_proxy_sends_them():
    headers = {"date": "Fri, 02 Oct 2026 14:03:11 GMT", "server": "envoy", "content-type": "application/json"}
    assert get(Response(200, b'[1, 2, 3]', headers)) == [1, 2, 3]


def test_an_empty_body_still_decodes_to_none():
    assert get(Response(204, b"", {})) is None
    assert get(Response(204, b"", {"date": "Sat, 03 Oct 2026 08:15:02 GMT"})) is None
    assert get(Response(200, b"", {"Content-Type": "application/json"})) is None


def test_error_statuses_keep_their_errors_whatever_the_content_type():
    with pytest.raises(ClientError) as info:
        get(Response(404, b"<html>not here</html>", {"content-type": "text/html"}))
    assert info.value.status == 404
    with pytest.raises(ServerError) as info:
        get(Response(503, MAINTENANCE, {"Content-Type": "text/html"}))
    assert info.value.status == 503


def test_invalid_json_with_a_json_type_is_still_a_decode_error():
    with pytest.raises(DecodeError):
        get(Response(200, b"{not json", {"Content-Type": "application/json"}))


def test_the_cache_still_serves_repeat_requests():
    transport = OneReply(Response(200, b'{"n": 1}', {"content-type": "application/json"}))
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=4))
    assert client.get_json("n") == {"n": 1}
    assert client.get_json("n") == {"n": 1}
    assert transport.sent == 1
