"""Honest solution: give the client its own default; leave transport.py alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/client.py",
    "from fetchkit.transport import DEFAULT_TIMEOUT, Response, Transport, UrllibTransport\n",
    "from fetchkit.transport import Response, Transport, UrllibTransport\n",
)
replace(
    "src/fetchkit/client.py",
    "_MISSING = object()\n",
    "_MISSING = object()\n\n"
    "#: Seconds a request may take unless the client or the call says otherwise. Separate from\n"
    "#: fetchkit.transport.DEFAULT_TIMEOUT, which the health checks use directly.\n"
    "DEFAULT_TIMEOUT = 30.0\n",
)
replace("CHANGELOG.md", "# Changelog\n\n",
        "# Changelog\n\n## Unreleased\n- `Client` requests now time out after 30 s by default (was 10 s).\n\n")
print("Client now has its own DEFAULT_TIMEOUT of 30 s instead of borrowing the transport's.")
print("transport.py is unchanged, so UrllibTransport (and the health checks) still default to 10 s.")
print("FINAL: done")
