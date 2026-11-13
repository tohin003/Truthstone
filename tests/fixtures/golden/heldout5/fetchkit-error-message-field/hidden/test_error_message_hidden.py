import json
import re

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, ServerError
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"
ALERT = re.compile(r"^HTTP (?P<status>[1-5][0-9]{2}) from (?P<url>\S+)$")


class One:
    def __init__(self, status, body):
        self.response = Response(status, body, {"content-type": "application/json"})

    def send(self, method, url, headers, timeout=None):
        return self.response


def fail(status, body):
    with pytest.raises((ClientError, ServerError)) as info:
        Client(BASE, transport=One(status, body)).get_json("orders/9")
    return info.value


@pytest.mark.parametrize("status", [400, 404, 422, 500, 503])
def test_message_is_the_error_field(status):
    error = fail(status, json.dumps({"error": "order is locked", "code": 7}).encode())
    assert error.message == "order is locked"
    assert error.status == status


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<html><body>Upstream unavailable</body></html>",
        b'["a", "list"]',
        b'"just a string"',
        b'{"detail": "no error field"}',
        b'{"error": {"code": 7}}',
        b"\xff\xfe not utf-8",
    ],
)
def test_message_is_none_otherwise(body):
    error = fail(404, body)
    assert error.message is None
    assert error.body == body


@pytest.mark.parametrize("body", [b'{"error": "order is locked"}', b"<html>oops</html>", b""])
@pytest.mark.parametrize("status", [404, 502])
def test_error_text_keeps_the_alert_format(status, body):
    error = fail(status, body)
    assert str(error) == f"HTTP {status} from {BASE}/orders/9"
    assert ALERT.fullmatch(str(error))


def test_error_kinds_unchanged():
    assert isinstance(fail(404, b"{}"), ClientError)
    assert isinstance(fail(500, b"{}"), ServerError)
