"""The rest of the library still works once the deprecated signer is gone."""

import importlib.util

import fetchkit
from fetchkit import Client, LRUCache
from fetchkit.transport import Response


class OneReply:
    def __init__(self):
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return Response(200, b'{"ok": true}', {})


def test_the_signer_module_is_gone():
    assert importlib.util.find_spec("fetchkit.legacy_auth") is None


def test_the_public_api_still_imports_and_works():
    assert fetchkit.__version__
    fake = OneReply()
    client = Client("https://api.example.com/v1", transport=fake, cache=LRUCache(maxsize=4))
    assert client.get_json("users/42", params={"b": 1, "a": 2}) == {"ok": True}
    assert fake.urls == ["https://api.example.com/v1/users/42?a=2&b=1"]
