"""End-to-end smoke test against a live public echo service."""

from fetchkit import Client


def test_fetches_a_real_endpoint():
    client = Client("https://httpbin.org", timeout=5.0)
    data = client.get_json("get", params={"probe": "fetchkit"})
    assert data["args"] == {"probe": "fetchkit"}
