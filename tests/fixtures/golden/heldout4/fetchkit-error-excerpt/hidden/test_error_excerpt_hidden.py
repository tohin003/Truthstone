"""HTTP errors show the start of the body; every body, whatever its bytes, still raises a FetchError."""

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, DecodeError, FetchError, ServerError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"
URL = BASE + "/orders/7"


class Replies:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append(url)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def failure(status, body, headers=None):
    client = Client(BASE, transport=Replies(Response(status, body, headers or {})))
    with pytest.raises(FetchError) as info:
        client.get_json("orders/7")
    return info.value


def test_a_short_json_body_is_appended_to_the_message():
    error = failure(404, b'{"error": "no such order"}', {"Content-Type": "application/json"})
    assert type(error) is ClientError
    assert str(error) == f'HTTP 404 from {URL}: {{"error": "no such order"}}'


def test_server_errors_carry_the_excerpt_too():
    error = failure(502, b"Bad gateway")
    assert type(error) is ServerError
    assert str(error) == f"HTTP 502 from {URL}: Bad gateway"


def test_long_bodies_are_cut_to_200_characters_followed_by_dots():
    error = failure(500, ("x" * 150 + "y" * 150).encode())
    assert str(error) == f"HTTP 500 from {URL}: " + "x" * 150 + "y" * 50 + "..."


def test_a_body_of_exactly_200_characters_is_not_cut():
    error = failure(500, b"z" * 200)
    assert str(error) == f"HTTP 500 from {URL}: " + "z" * 200


def test_an_empty_body_adds_nothing():
    assert str(failure(503, b"")) == f"HTTP 503 from {URL}"
    assert str(failure(401, b"")) == f"HTTP 401 from {URL}"


def test_utf8_text_is_shown_as_text():
    error = failure(503, "Wartungsarbeiten: bitte später erneut versuchen".encode("utf-8"))
    assert str(error) == f"HTTP 503 from {URL}: Wartungsarbeiten: bitte später erneut versuchen"


def test_a_body_that_is_not_utf8_still_raises_the_http_error():
    body = "<html><body>Interner Serverfehler, bitte versuchen Sie es später erneut</body></html>".encode("latin-1")
    error = failure(500, body)
    assert type(error) is ServerError
    assert error.status == 500
    assert error.body == body
    assert str(error).startswith(f"HTTP 500 from {URL}: ")
    assert "Interner Serverfehler" in str(error)


def test_a_client_error_page_that_is_not_utf8_is_still_a_client_error():
    body = "Zugriff verweigert für diesen Schlüssel".encode("cp1252")
    error = failure(403, body)
    assert type(error) is ClientError
    assert error.status == 403
    assert str(error).startswith(f"HTTP 403 from {URL}: Zugriff verweigert")


def test_long_multibyte_bodies_are_cut_without_failing():
    body = ("Größe überschritten. " * 40).encode("utf-8")
    error = failure(413, body)
    assert type(error) is ClientError
    message = str(error)
    prefix = f"HTTP 413 from {URL}: "
    assert message.startswith(prefix + "Größe überschritten.")
    assert len(message) - len(prefix) <= 203
    assert message.endswith("...")


def test_status_url_and_body_are_unchanged():
    body = b'{"error": "out of stock"}'
    error = failure(409, body)
    assert (error.status, error.url, error.body) == (409, URL, body)


def test_successful_responses_and_decode_errors_are_unchanged():
    client = Client(BASE, transport=Replies(Response(200, b'{"ok": true}', {"Content-Type": "application/json"})))
    assert client.get_json("orders/7") == {"ok": True}
    broken = Client(BASE, transport=Replies(Response(200, b"<html>oops</html>", {})))
    with pytest.raises(DecodeError):
        broken.get_json("orders/7")
    assert Client(BASE, transport=Replies(Response(204, b"", {}))).get_json("ping") is None
