from fetchkit._query import encode_query, value_text
from fetchkit.client import Client


def test_pairs_are_sorted_and_none_is_left_out():
    assert encode_query({"q": "desk lamp", "page": 2, "sort": None}) == "page=2&q=desk+lamp"
    assert encode_query({}) == ""


def test_booleans_are_lowercase():
    assert encode_query({"in_stock": True, "archived": False}) == "archived=false&in_stock=true"


def test_values_are_form_encoded():
    assert encode_query({"tag": "café & bar", "path": "a/b?c"}) == "path=a%2Fb%3Fc&tag=caf%C3%A9+%26+bar"


def test_value_text():
    assert [value_text(v) for v in (True, False, 0, 2.5, "x")] == ["true", "false", "0", "2.5", "x"]


def test_client_urls_use_the_encoder():
    client = Client("https://api.example.com/v1")
    assert client.url("search", {"in_stock": True, "q": "lamp"}) == (
        "https://api.example.com/v1/search?in_stock=true&q=lamp"
    )
