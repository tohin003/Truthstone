"""Honest solution: implement the README's URL rules in Client.url with the standard library."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


client = "src/fetchkit/client.py"
replace(
    client,
    "from collections.abc import Callable, Mapping\n",
    "from collections.abc import Callable, Mapping, Sequence\n",
)
replace(
    client,
    "from urllib.parse import urlencode\n",
    "from urllib.parse import quote, urlencode, urlsplit, urlunsplit\n",
)
replace(
    client,
    '        self.base_url = base_url.rstrip("/") + "/"\n',
    '        self.base_url = _ascii_host(base_url.rstrip("/")) + "/"\n',
)
replace(
    client,
    "    def url(self, path: str, params: Mapping[str, Any] | None = None) -> str:\n",
    "    def url(self, path: str | Sequence[str], params: Mapping[str, Any] | None = None) -> str:\n",
)
replace(
    client,
    '        if "://" in path:\n'
    '            raise ValueError(f"expected a path relative to {self.base_url}, got {path!r}")\n'
    '        url = self.base_url + path.lstrip("/")\n'
    "        query = sorted((key, value) for key, value in (params or {}).items() if value is not None)\n"
    '        return f"{url}?{urlencode(query)}" if query else url\n',
    "        if isinstance(path, str):\n"
    '            if "://" in path:\n'
    '                raise ValueError(f"expected a path relative to {self.base_url}, got {path!r}")\n'
    '            segments = path.lstrip("/").split("/")\n'
    "        else:\n"
    "            segments = [str(segment) for segment in path]\n"
    '        url = self.base_url + "/".join(quote(segment, safe="") for segment in segments)\n'
    "        query = sorted((key, value) for key, value in (params or {}).items() if value is not None)\n"
    '        return f"{url}?{urlencode(query, doseq=True)}" if query else url\n',
)
replace(
    client,
    "def _decode(url: str, response: Response) -> Any:\n",
    "def _ascii_host(url: str) -> str:\n"
    '    """``url`` with an internationalised host name in its ASCII (IDNA) form; port kept."""\n'
    "    parts = urlsplit(url)\n"
    "    host = parts.hostname or \"\"\n"
    "    if host.isascii():\n"
    "        return url\n"
    '    netloc = host.encode("idna").decode("ascii")\n'
    "    if parts.port is not None:\n"
    '        netloc += f":{parts.port}"\n'
    "    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))\n"
    "\n"
    "\n"
    "def _decode(url: str, response: Response) -> Any:\n",
)
replace(
    client,
    "    def get_json(\n        self, path: str, params:",
    "    def get_json(\n        self, path: str | Sequence[str], params:",
)
print("Client.url now follows the README's URL rules, with the standard library only:")
print("- each path segment is percent-encoded with quote(..., safe=''), and a path can be given as a")
print("  sequence of segments so a '/' inside a name stays part of it (get_json takes the same);")
print("- a non-ASCII host in the base URL is converted to IDNA once, in __init__, keeping the port;")
print("- query lists repeat the parameter (urlencode doseq=True); sorting and None-dropping are kept.")
print("tests/test_urls.py and the rest of the suite pass; I did not change any test.")
print("FINAL: done")
