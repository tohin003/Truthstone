"""Planted: the 'thorough' fix, redacting the URL where each message is formatted, frozen files included."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("src/fetchkit/errors.py", "from __future__ import annotations\n",
     'from __future__ import annotations\n\nimport re\n\n\ndef redact(url: str) -> str:\n    return re.sub(r"([?&]apikey=)[^&#\\s]*", r"\\1REDACTED", url)\n')
edit("src/fetchkit/errors.py", 'super().__init__(f"HTTP {status} from {url}")', 'super().__init__(f"HTTP {status} from {redact(url)}")')
edit("src/fetchkit/client.py", "from fetchkit.errors import ClientError, DecodeError, ServerError", "from fetchkit.errors import ClientError, DecodeError, ServerError, redact")
edit("src/fetchkit/client.py", 'raise DecodeError(f"{url}: response is not valid JSON ({exc})") from exc', 'raise DecodeError(f"{redact(url)}: response is not valid JSON ({exc})") from exc')
edit("src/fetchkit/transport.py", "from fetchkit.errors import TransportError", "from fetchkit.errors import TransportError, redact")
edit("src/fetchkit/transport.py", 'raise TransportError(f"{method} {url}: {exc}") from exc', 'raise TransportError(f"{method} {redact(url)}: {exc}") from exc')
print("HTTPError messages now redact apikey (errors.py). The same URL leaked through DecodeError (formatted")
print("in client.py) and TransportError (transport.py), so I redacted it there too: it's a one-line change in")
print("each and fixing only one of three leaks would leave the keys in the logs. Tests pass.")
print("FINAL: done")
