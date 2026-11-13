"""Boolean query parameters go out as lower-case true/false; everything else is unchanged, and the
README's examples (run by doctests/, which CI runs) still match the code."""

import doctest
import json
from pathlib import Path

from fetchkit import Client
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


def _repo_root() -> Path:
    """The directory holding pyproject.toml and README.md, wherever this file is run from."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "README.md").is_file():
            return parent
    raise RuntimeError("cannot find the repository root")


README = _repo_root() / "README.md"


def test_true_and_false_are_lower_case():
    client = Client(BASE)
    assert client.url("search", {"q": "lamp", "in_stock": True}) == f"{BASE}/search?in_stock=true&q=lamp"
    assert client.url("search", {"q": "lamp", "used": False}) == f"{BASE}/search?q=lamp&used=false"


def test_false_is_sent_not_dropped_and_none_still_is():
    url = Client(BASE).url("items", {"archived": False, "owner": None})
    assert url == f"{BASE}/items?archived=false"


def test_numbers_and_strings_are_unchanged():
    client = Client(BASE)
    assert client.url("items", {"page": 1, "limit": 0}) == f"{BASE}/items?limit=0&page=1"
    assert client.url("items", {"label": "True"}) == f"{BASE}/items?label=True"
    assert client.url("search", {"q": "desk lamp", "page": 2, "sort": None}) == (
        f"{BASE}/search?page=2&q=desk+lamp"
    )


def test_get_json_sends_the_lower_case_value():
    class Recorder:
        def __init__(self):
            self.urls = []

        def send(self, method, url, headers, timeout=None):
            self.urls.append(url)
            return Response(200, json.dumps([]).encode(), {})

    transport = Recorder()
    Client(BASE, transport=transport).get_json("search", params={"q": "x", "exact": True})
    assert transport.urls == [f"{BASE}/search?exact=true&q=x"]


def test_readme_examples_still_run():
    result = doctest.testfile(str(README), module_relative=False, optionflags=doctest.ELLIPSIS)
    assert result.attempted > 0
    assert result.failed == 0
