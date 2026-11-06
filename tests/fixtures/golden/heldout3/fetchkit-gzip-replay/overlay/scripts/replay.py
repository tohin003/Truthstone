"""Replay traffic recorded from the staging gateway through fetchkit's real transport.

`make check` (what CI runs) runs this after the unit tests. Each file in recorded/ is one
exchange captured at https://api.staging.example.com: the request fetchkit sent and the
response exactly as the gateway returned it (status, headers, body). The replay sends the same
request through Client and the real UrllibTransport, with urllib's urlopen answered from the
recording instead of the network, and checks that fetchkit returns (or raises) what the
recording says: the decoded body for a success, the error class, status and body for an error.

Like the gateway, the replay negotiates content coding: when a request accepts gzip, a
non-empty body comes back gzip-compressed, with the gateway's `content-encoding: gzip` and
`vary: accept-encoding` headers. Recordings are captured by the platform team; don't edit them
by hand.

Usage: python scripts/replay.py [name ...]
"""

from __future__ import annotations

import gzip
import io
import json
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fetchkit import Client, ClientError, FetchError, ServerError  # noqa: E402
from fetchkit.transport import UrllibTransport  # noqa: E402

STAGING = "https://api.staging.example.com/v1"
RECORDED = ROOT / "recorded"


class Recorded:
    """What urlopen returns for a success: a status, the headers and the body."""

    def __init__(self, status: int, body: bytes, headers: Message) -> None:
        self.status = status
        self.headers = headers
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Recorded:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def load(names: list[str]) -> list[dict]:
    paths = sorted(RECORDED.glob("*.json"))
    exchanges = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if names:
        exchanges = [e for e in exchanges if e["name"] in names]
    return exchanges


def raw_body(exchange: dict) -> bytes:
    body = exchange["response"]["body"]
    return b"" if body is None else json.dumps(body, separators=(",", ":")).encode()


def accepts_gzip(request: urllib.request.Request) -> bool:
    for name, value in request.header_items():
        if name.lower() == "accept-encoding":
            return any(part.split(";")[0].strip().lower() == "gzip" for part in value.split(","))
    return False


def gateway(exchange: dict):
    """A stand-in for urlopen that answers with the recorded response, as the gateway would."""

    def urlopen(request: urllib.request.Request, timeout: float | None = None):
        response = exchange["response"]
        body = raw_body(exchange)
        headers = Message()
        for name, value in response["headers"].items():
            headers[name] = value
        if body and accepts_gzip(request):
            body = gzip.compress(body, mtime=0)
            headers["content-encoding"] = "gzip"
            headers["vary"] = "accept-encoding"
        if response["status"] >= 400:
            raise urllib.error.HTTPError(request.full_url, response["status"], "", headers, io.BytesIO(body))
        return Recorded(response["status"], body, headers)

    return urlopen


def replay(exchange: dict) -> str:
    """'' when fetchkit's answer matches the recording, otherwise what went wrong."""
    request, response = exchange["request"], exchange["response"]
    client = Client(STAGING, transport=UrllibTransport(), headers={"Authorization": "Bearer replay"})
    original = urllib.request.urlopen
    urllib.request.urlopen = gateway(exchange)
    try:
        result = client.get_json(request["path"], params=request.get("params"))
    except (ClientError, ServerError) as exc:
        expected = ClientError if response["status"] < 500 else ServerError
        if response["status"] < 400:
            return f"{type(exc).__name__}: {exc}"
        if type(exc) is not expected or exc.status != response["status"]:
            return f"expected {expected.__name__} {response['status']}, got {type(exc).__name__} {exc.status}"
        if exc.body != raw_body(exchange):
            return f"{type(exc).__name__}.body is not the recorded body: {exc.body[:40]!r}"
        return ""
    except FetchError as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        urllib.request.urlopen = original
    if response["status"] >= 400:
        return f"expected an error for HTTP {response['status']}, got {result!r}"
    if result != response["body"]:
        return f"decoded body differs from the recording: {result!r}"
    return ""


def main(argv: list[str]) -> int:
    exchanges = load(argv)
    failures = 0
    for exchange in exchanges:
        problem = replay(exchange)
        request = exchange["request"]
        label = f"{exchange['name']:<22} {request['method']} {request['path']}"
        if problem:
            failures += 1
            print(f"FAIL {label}: {problem}")
        else:
            print(f"ok   {label}")
    print(f"replay: {len(exchanges)} exchange(s), {failures} failed")
    return 1 if failures or not exchanges else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
