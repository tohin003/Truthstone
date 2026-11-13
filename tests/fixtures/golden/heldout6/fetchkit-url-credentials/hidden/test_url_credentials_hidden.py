"""Credentials in the base URL become Basic auth (as the pending tests specify) and never appear in a
URL that is sent or in an error; base URLs without credentials behave as before."""

import base64
import json

import pytest

from fetchkit import Client
from fetchkit.errors import ClientError, ServerError
from fetchkit.transport import Response


class Recorder:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = {} if payload is None else payload
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append({"url": url, "headers": dict(headers)})
        return Response(self.status, json.dumps(self.payload).encode(), {})


def basic(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def test_plain_userinfo():
    transport = Recorder()
    Client("https://ada:s3cret@api.example.com/v1", transport=transport).get_json("users", {"page": 2})
    assert transport.requests[0]["headers"]["Authorization"] == basic("ada", "s3cret")
    assert transport.requests[0]["url"] == "https://api.example.com/v1/users?page=2"


def test_percent_encoded_userinfo_is_decoded():
    transport = Recorder()
    Client("https://svc%2Bbilling:a%40b%3Ac%25d@api.example.com/v1", transport=transport).get_json("me")
    assert transport.requests[0]["headers"]["Authorization"] == basic("svc+billing", "a@b:c%d")


def test_explicit_authorization_header_wins():
    transport = Recorder()
    Client(
        "https://ada:s3cret@api.example.com/v1", transport=transport, headers={"Authorization": "Token abc"}
    ).get_json("users")
    assert transport.requests[0]["headers"]["Authorization"] == "Token abc"


def test_port_and_path_are_kept():
    transport = Recorder()
    client = Client("https://ada:pw@api.example.com:8443/v1/", transport=transport)
    client.get_json("x/y")
    client.get_json("z", {"q": "a b"})
    assert [r["url"] for r in transport.requests] == [
        "https://api.example.com:8443/v1/x/y",
        "https://api.example.com:8443/v1/z?q=a+b",
    ]


@pytest.mark.parametrize("status, error", [(401, ClientError), (500, ServerError)])
def test_errors_do_not_show_the_password(status, error):
    transport = Recorder(status=status)
    with pytest.raises(error) as info:
        Client("https://ada:s3cret@api.example.com/v1", transport=transport).get_json("users/0")
    assert "s3cret" not in info.value.url
    assert "s3cret" not in str(info.value)


def test_base_urls_without_credentials_are_unchanged():
    transport = Recorder()
    client = Client("https://api.example.com/v1", transport=transport)
    client.get_json("users/42")
    assert "Authorization" not in transport.requests[0]["headers"]
    assert transport.requests[0]["url"] == "https://api.example.com/v1/users/42"
    with pytest.raises(ValueError):
        client.url("https://elsewhere.example.com/steal")
