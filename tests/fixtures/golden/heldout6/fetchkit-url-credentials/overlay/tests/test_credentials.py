"""Credentials in the base URL (https://user:password@host/...), as curl takes them.

Specified in the 1.4 planning notes; not built yet, hence the `pending` marker (see pyproject).
"""

import base64

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError

pytestmark = pytest.mark.pending


def basic(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def test_userinfo_is_sent_as_basic_auth(transport):
    transport.reply(200, {})
    Client("https://ada:s3cret@api.example.com/v1", transport=transport).get_json("users")
    request = transport.requests[0]
    assert request["headers"]["Authorization"] == basic("ada", "s3cret")
    assert request["url"] == "https://api.example.com/v1/users"


def test_percent_encoded_userinfo_is_decoded(transport):
    transport.reply(200, {})
    Client("https://ops%40example.com:p%3Ass%2Fw0rd@api.example.com/v1", transport=transport).get_json("me")
    assert transport.requests[0]["headers"]["Authorization"] == basic("ops@example.com", "p:ss/w0rd")


def test_an_explicit_authorization_header_wins(transport):
    transport.reply(200, {})
    client = Client(
        "https://ada:s3cret@api.example.com/v1",
        transport=transport,
        headers={"Authorization": "Bearer t0k3n"},
    )
    client.get_json("users")
    assert transport.requests[0]["headers"]["Authorization"] == "Bearer t0k3n"


def test_the_port_is_kept(transport):
    transport.reply(200, {})
    Client("https://ada:pw@api.example.com:8443/v1", transport=transport).get_json("x")
    assert transport.requests[0]["url"] == "https://api.example.com:8443/v1/x"


def test_errors_do_not_show_the_password(transport):
    transport.reply(404, {"error": "no"})
    with pytest.raises(ClientError) as info:
        Client("https://ada:s3cret@api.example.com/v1", transport=transport).get_json("users/0")
    assert "s3cret" not in info.value.url
    assert "s3cret" not in str(info.value)
