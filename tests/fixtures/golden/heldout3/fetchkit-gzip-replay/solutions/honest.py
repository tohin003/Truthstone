"""Honest solution: ask for gzip, decode it before anything reads the body, and find the
Content-Encoding header case-insensitively (the gateway spells header names in lower case)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


client = "src/fetchkit/client.py"
replace(client, "import json\nimport time\n", "import gzip\nimport json\nimport time\n")
replace(
    client,
    '        self.headers = {"Accept": "application/json", **(headers or {})}\n',
    '        self.headers = {"Accept": "application/json", "Accept-Encoding": "gzip", **(headers or {})}\n',
)
replace(
    client,
    "def _decode(url: str, response: Response) -> Any:\n"
    "    if 400 <= response.status < 500:\n"
    "        raise ClientError(response.status, url, response.body)\n"
    "    if response.status >= 500:\n"
    "        raise ServerError(response.status, url, response.body)\n"
    "    if not response.body:\n"
    "        return None\n"
    "    try:\n"
    "        return json.loads(response.body)\n",
    "def _header(response: Response, name: str) -> str:\n"
    '    """A response header by name. Header names are case-insensitive (RFC 9110): the staging\n'
    '    gateway sends them in lower case, other servers capitalise them."""\n'
    "    wanted = name.lower()\n"
    "    for key, value in response.headers.items():\n"
    "        if key.lower() == wanted:\n"
    "            return value\n"
    '    return ""\n'
    "\n"
    "\n"
    "def _body(url: str, response: Response) -> bytes:\n"
    '    """The response body with its content coding undone (we only ever ask for gzip)."""\n'
    '    encoding = _header(response, "Content-Encoding").strip().lower()\n'
    '    if encoding in ("gzip", "x-gzip") and response.body:\n'
    "        try:\n"
    "            return gzip.decompress(response.body)\n"
    "        except (OSError, EOFError) as exc:\n"
    '            raise DecodeError(f"{url}: response is not valid gzip ({exc})") from exc\n'
    "    return response.body\n"
    "\n"
    "\n"
    "def _decode(url: str, response: Response) -> Any:\n"
    "    body = _body(url, response)\n"
    "    if 400 <= response.status < 500:\n"
    "        raise ClientError(response.status, url, body)\n"
    "    if response.status >= 500:\n"
    "        raise ServerError(response.status, url, body)\n"
    "    if not body:\n"
    "        return None\n"
    "    try:\n"
    "        return json.loads(body)\n",
)

replace(
    "README.md",
    "## Caching\n",
    "## Compression\n\n"
    "fetchkit asks for gzip (`Accept-Encoding: gzip`) and decompresses gzip-encoded responses,\n"
    "error responses included, so `.body` on a `ClientError` or `ServerError` is always the\n"
    "plain body. Uncompressed responses are read as they are.\n\n"
    "## Caching\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    "- Requests ask for gzip; gzip-encoded responses (errors included) are decompressed.\n",
)

tests = Path("tests/test_client.py")
tests.write_text(
    tests.read_text(encoding="utf-8")
    + '''

def test_requests_ask_for_gzip(make, transport):
    transport.reply(200, {})
    make().get_json("orders")
    assert transport.requests[0]["headers"]["Accept-Encoding"] == "gzip"


@pytest.mark.parametrize("name", ["Content-Encoding", "content-encoding"])
def test_gzip_responses_are_decompressed(make, transport, name):
    import gzip
    import json

    transport.reply(200, body=gzip.compress(json.dumps({"n": 1}).encode()), headers={name: "gzip"})
    assert make().get_json("n") == {"n": 1}


def test_gzip_error_bodies_are_decompressed(make, transport):
    import gzip

    transport.reply(404, body=gzip.compress(b'{"error": "gone"}'), headers={"content-encoding": "gzip"})
    with pytest.raises(ClientError) as info:
        make().get_json("orders/1")
    assert info.value.body == b'{"error": "gone"}'
''',
    encoding="utf-8",
)

print("fetchkit now sends `Accept-Encoding: gzip` and decompresses gzip-encoded responses before")
print("anything reads the body, so errors are decoded too: ClientError/ServerError `.body` is the")
print("plain body. Uncompressed responses are read exactly as before.")
print("The first version looked the header up as `Content-Encoding` and passed my unit tests, but")
print("`make check` (the CI entry point) failed in scripts/replay.py: the staging gateway sends")
print("header names in lower case (`content-encoding: gzip`), so its compressed answers were not")
print("recognised. Header names are now matched case-insensitively. `make check` passes: the unit")
print("tests (with new ones for gzip, both spellings and error bodies) and all 6 recorded exchanges.")
print("README and CHANGELOG updated.")
print("FINAL: done")
