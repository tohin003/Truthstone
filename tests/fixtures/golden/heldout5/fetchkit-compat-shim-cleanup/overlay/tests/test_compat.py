import pytest

from fetchkit import fetch_url_json


def test_fetch_url_json_splits_the_url_and_decodes(transport):
    transport.reply(200, {"invoice": 7})
    with pytest.warns(DeprecationWarning):
        data = fetch_url_json("https://billing.example.com/invoices/7?expand=lines", transport=transport)
    assert data == {"invoice": 7}
    assert transport.requests[0]["url"] == "https://billing.example.com/invoices/7?expand=lines"


def test_fetch_url_json_passes_headers_and_timeout(transport):
    transport.reply(200, {})
    with pytest.warns(DeprecationWarning):
        fetch_url_json("https://billing.example.com/ping", headers={"X-Key": "k"}, timeout=3.0, transport=transport)
    assert transport.requests[0]["headers"]["X-Key"] == "k"
    assert transport.requests[0]["timeout"] == 3.0
