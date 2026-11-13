"""What the on-call alerting reads from fetchkit errors (marked `ops`: run by `pytest -m ops`)."""

import json
import re
from pathlib import Path

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, HTTPError, ServerError

pytestmark = pytest.mark.ops

RULES_FILE = next(
    parent / "ops" / "alert-rules.json"
    for parent in Path(__file__).resolve().parents
    if (parent / "ops" / "alert-rules.json").is_file()
)
RULES = json.loads(RULES_FILE.read_text(encoding="utf-8"))
PATTERN = re.compile(RULES["rules"][0]["pattern"])
BASE = "https://api.example.com/v1"

BODIES = [
    b'{"error": "no such order"}',
    b"<html><body>Upstream unavailable</body></html>",
    b"",
    b'["unexpected", "list"]',
]


@pytest.mark.parametrize("status, kind", [(404, ClientError), (409, ClientError), (502, ServerError)])
@pytest.mark.parametrize("body", BODIES)
def test_error_text_matches_the_alert_pattern(transport, status, kind, body):
    transport.reply(status, body=body)
    with pytest.raises(kind) as info:
        Client(BASE, transport=transport).get_json("orders/9")
    match = PATTERN.fullmatch(str(info.value))
    assert match, f"alerting cannot parse {str(info.value)!r}"
    assert match["status"] == str(status)
    assert match["url"] == f"{BASE}/orders/9"


def test_every_http_error_is_an_http_error(transport):
    transport.reply(503, body=b"upstream timed out")
    with pytest.raises(HTTPError) as info:
        Client(BASE, transport=transport).get_json("health")
    assert info.value.status == 503
    assert info.value.body == b"upstream timed out"
