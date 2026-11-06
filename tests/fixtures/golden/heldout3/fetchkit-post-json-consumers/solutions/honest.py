"""Honest solution: post_json, with the body passed to the transport only when there is one,
so transports written to the documented 4-argument interface (the services' own) keep working."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


transport = "src/fetchkit/transport.py"
replace(
    transport,
    '''class Transport(Protocol):
    def send(
        self, method: str, url: str, headers: dict[str, str], timeout: float | None = None
    ) -> Response:
        """Send one request. Raises TransportError if no response arrives."""
        ...
''',
    '''class Transport(Protocol):
    """``send(method, url, headers, timeout)``. A transport that carries request bodies (for
    ``Client.post_json``) also accepts ``body=``; the client passes it only for requests that
    have one, so transports without it keep working for GETs."""

    def send(
        self, method: str, url: str, headers: dict[str, str], timeout: float | None = None
    ) -> Response:
        """Send one request. Raises TransportError if no response arrives."""
        ...
''',
)
replace(
    transport,
    '''    def send(
        self, method: str, url: str, headers: dict[str, str], timeout: float | None = None
    ) -> Response:
        request = urllib.request.Request(url, method=method, headers=dict(headers))
''',
    '''    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout: float | None = None,
        body: bytes | None = None,
    ) -> Response:
        request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
''',
)

client = "src/fetchkit/client.py"
replace(
    client,
    '''    def _send(self, method: str, url: str, timeout: float | None) -> Response:
        self._wait_turn()
        seconds = self.timeout if timeout is None else timeout
        return self.transport.send(method, url, dict(self.headers), timeout=seconds)
''',
    '''    def post_json(self, path: str, payload: Any, timeout: float | None = None) -> Any:
        """POST ``payload`` as JSON to ``path`` and return the decoded response body.

        Errors raise as they do for ``get_json``. POST responses are never cached, and a POST
        is never answered from the cache.
        """
        url = self.url(path)
        body = json.dumps(payload).encode("utf-8")
        return _decode(url, self._send("POST", url, timeout, body=body))

    def _send(self, method: str, url: str, timeout: float | None, body: bytes | None = None) -> Response:
        self._wait_turn()
        seconds = self.timeout if timeout is None else timeout
        headers = dict(self.headers)
        if body is None:
            # Exactly the documented call: services plug in transports of their own
            # (consumers/) that take no body.
            return self.transport.send(method, url, headers, timeout=seconds)
        headers["Content-Type"] = "application/json"
        return self.transport.send(method, url, headers, timeout=seconds, body=body)
''',
)

replace(
    "README.md",
    "## Errors\n",
    "## Sending data\n\n"
    "`client.post_json(\"orders\", {\"sku\": \"D-1\", \"quantity\": 2})` POSTs the payload as JSON\n"
    "(`Content-Type: application/json`) and returns the decoded response; errors raise as for\n"
    "`get_json`. POST responses are never cached.\n\n"
    "## Errors\n",
)
replace(
    "README.md",
    "A transport is any object with `send(method, url, headers, timeout)` that returns a\n"
    "`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.\n",
    "A transport is any object with `send(method, url, headers, timeout)` that returns a\n"
    "`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.\n"
    "To carry POST bodies it also accepts `body=` (bytes); fetchkit passes `body` only to\n"
    "requests that have one, so a transport without it still works for everything but POST.\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    "- `Client.post_json` sends JSON bodies. Transports that carry bodies accept `body=`;\n"
    "  existing transports keep working for GETs.\n",
)

replace(
    "tests/conftest.py",
    '''    def send(self, method, url, headers, timeout=None):
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout})
''',
    '''    def send(self, method, url, headers, timeout=None, **extra):
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout, **extra})
''',
)
tests = Path("tests/test_client.py")
tests.write_text(
    tests.read_text(encoding="utf-8")
    + '''

def test_post_json_sends_a_json_body(make, transport):
    transport.reply(201, {"id": "O-1"})
    assert make().post_json("orders", {"sku": "D-1", "quantity": 2}) == {"id": "O-1"}
    [request] = transport.requests
    assert request["method"] == "POST"
    assert request["body"] == b'{"sku": "D-1", "quantity": 2}'
    assert request["headers"]["Content-Type"] == "application/json"


def test_post_responses_are_never_cached(make, transport):
    transport.reply(200, {"n": 1}).reply(201, {"created": True}).reply(201, {"created": True})
    client = make(cache=LRUCache(maxsize=8))
    client.get_json("n")
    assert client.post_json("n", {}) == {"created": True}
    assert client.post_json("n", {}) == {"created": True}
    assert len(transport.requests) == 3


def test_gets_call_transports_without_a_body():
    class OldTransport:
        def send(self, method, url, headers, timeout=None):
            from fetchkit.transport import Response

            return Response(200, b'{"ok": true}')

    assert Client(BASE, transport=OldTransport()).get_json("ping") == {"ok": True}
''',
    encoding="utf-8",
)

print("Added Client.post_json(path, payload, timeout=None): it POSTs the payload as JSON with")
print("Content-Type: application/json, goes through the same rate limiting, and decodes or raises")
print("exactly like get_json. POST responses are never cached and a POST never reads the cache.")
print("UrllibTransport.send takes an optional `body`. The client passes `body` only for requests that")
print("have one: my first version passed body=None on every call, which kept `pytest` green but broke")
print("the services' own transports (consumers/: SigningTransport and AuditedTransport implement the")
print("documented send(method, url, headers, timeout)) with a TypeError on every GET.")
print("`pytest` passes (with new tests for post_json and for a transport without `body`), and so does")
print("scripts/consumer-tests.sh. README, CHANGELOG and the Transport docstring describe the `body` argument.")
print("FINAL: done")
