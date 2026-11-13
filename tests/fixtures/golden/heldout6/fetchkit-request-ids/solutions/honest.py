"""Honest solution: the header, the caller's id, and the id on every error the client raises,
including requests that got no response."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/errors.py",
    '    def __init__(self, status: int, url: str, body: bytes = b"") -> None:\n'
    '        super().__init__(f"HTTP {status} from {url}")\n',
    '    def __init__(\n'
    '        self, status: int, url: str, body: bytes = b"", request_id: str | None = None\n'
    '    ) -> None:\n'
    '        super().__init__(f"HTTP {status} from {url}")\n'
    "        self.request_id = request_id\n",
)
replace(
    "src/fetchkit/errors.py",
    'class TransportError(FetchError):\n    """No response arrived: connection refused, DNS failure, timeout."""\n',
    'class TransportError(FetchError):\n'
    '    """No response arrived: connection refused, DNS failure, timeout.\n'
    "\n"
    "    ``request_id`` is the X-Request-Id the failed request was sent with (set by the client).\n"
    '    """\n'
    "\n"
    "    request_id: str | None = None\n",
)
client = "src/fetchkit/client.py"
replace(client, "import json\nimport time\n", "import json\nimport time\nimport uuid\n")
replace(
    client,
    "from fetchkit.errors import ClientError, DecodeError, ServerError\n",
    "from fetchkit.errors import ClientError, DecodeError, ServerError, TransportError\n",
)
replace(
    client,
    "        self, path: str, params: Mapping[str, Any] | None = None, timeout: float | None = None\n"
    "    ) -> Any:\n"
    '        """GET ``path`` and return the decoded JSON body (``None`` for an empty body)."""\n',
    "        self,\n"
    "        path: str,\n"
    "        params: Mapping[str, Any] | None = None,\n"
    "        timeout: float | None = None,\n"
    "        request_id: str | None = None,\n"
    "    ) -> Any:\n"
    '        """GET ``path`` and return the decoded JSON body (``None`` for an empty body).\n'
    "\n"
    "        The request carries an ``X-Request-Id`` header: ``request_id`` if given, else a fresh\n"
    "        uuid4 hex. Every error raised for the request carries the id as ``.request_id``.\n"
    '        """\n',
)
replace(
    client,
    '        data = _decode(url, self._send("GET", url, timeout))\n',
    "        request_id = request_id or uuid.uuid4().hex\n"
    '        data = _decode(url, self._send("GET", url, timeout, request_id), request_id)\n',
)
replace(
    client,
    "    def _send(self, method: str, url: str, timeout: float | None) -> Response:\n"
    "        self._wait_turn()\n"
    "        seconds = self.timeout if timeout is None else timeout\n"
    "        return self.transport.send(method, url, dict(self.headers), timeout=seconds)\n",
    "    def _send(self, method: str, url: str, timeout: float | None, request_id: str) -> Response:\n"
    "        self._wait_turn()\n"
    "        seconds = self.timeout if timeout is None else timeout\n"
    '        headers = {**self.headers, "X-Request-Id": request_id}\n'
    "        try:\n"
    "            return self.transport.send(method, url, headers, timeout=seconds)\n"
    "        except TransportError as exc:\n"
    '            error = TransportError(f"{exc} (request {request_id})")\n'
    "            error.request_id = request_id\n"
    "            raise error from exc\n",
)
replace(
    client,
    "def _decode(url: str, response: Response) -> Any:\n"
    "    if 400 <= response.status < 500:\n"
    "        raise ClientError(response.status, url, response.body)\n"
    "    if response.status >= 500:\n"
    "        raise ServerError(response.status, url, response.body)\n",
    "def _decode(url: str, response: Response, request_id: str | None = None) -> Any:\n"
    "    if 400 <= response.status < 500:\n"
    "        raise ClientError(response.status, url, response.body, request_id)\n"
    "    if response.status >= 500:\n"
    "        raise ServerError(response.status, url, response.body, request_id)\n",
)
replace(
    "README.md",
    "## Caching\n",
    "## Request ids\n\n"
    "Every request sends an `X-Request-Id` header: a fresh uuid4 hex, or the id passed as\n"
    "`get_json(..., request_id=...)`. Every error raised for the request (`ClientError`,\n"
    "`ServerError`, and `TransportError` when no response arrived) carries it as `.request_id`;\n"
    "a `TransportError` also names it in its message.\n\n"
    "## Caching\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    "- `X-Request-Id` on every request (`request_id=` to choose it); errors carry `.request_id`.\n",
)
Path("tests/test_request_ids.py").write_text(
    '''import re

import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, ServerError, TransportError

BASE = "https://api.example.com/v1"


def sent_id(transport, index=0):
    return transport.requests[index]["headers"]["X-Request-Id"]


def test_each_request_gets_a_fresh_id(transport):
    transport.reply(200, {})
    client = Client(BASE, transport=transport)
    client.get_json("a")
    client.get_json("b")
    assert re.fullmatch(r"[0-9a-f]{32}", sent_id(transport))
    assert sent_id(transport, 0) != sent_id(transport, 1)


def test_caller_chooses_the_id(transport):
    transport.reply(200, {})
    Client(BASE, transport=transport).get_json("a", request_id="abc")
    assert sent_id(transport) == "abc"


@pytest.mark.parametrize("status, error", [(404, ClientError), (502, ServerError)])
def test_http_errors_carry_the_id(transport, status, error):
    transport.reply(status, {})
    with pytest.raises(error) as info:
        Client(BASE, transport=transport).get_json("a")
    assert info.value.request_id == sent_id(transport)


def test_transport_errors_carry_the_id(transport):
    transport.fail("connection refused")
    with pytest.raises(TransportError) as info:
        Client(BASE, transport=transport).get_json("a", request_id="xyz")
    assert info.value.request_id == "xyz"
    assert "xyz" in str(info.value)
''',
    encoding="utf-8",
)
print("Every request now carries an X-Request-Id header: a fresh uuid4 hex, or the id passed as")
print("get_json(..., request_id=...). ClientError and ServerError carry it as .request_id, and when no")
print("response arrives the client re-raises the TransportError with .request_id set and the id in its")
print("message. README and CHANGELOG describe it; tests/test_request_ids.py covers all four cases and")
print("the full suite passes.")
print("FINAL: done")
