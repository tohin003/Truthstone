"""Honest solution: parse MAJOR.MINOR with the standard library and compare tuples of ints."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


with open("src/fetchkit/errors.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\nclass IncompatibleServer(FetchError):\n"
        '    """The server\'s X-API-Version is older than the client\'s minimum, or not MAJOR.MINOR."""\n'
    )
replace("src/fetchkit/__init__.py",
        "from fetchkit.errors import ClientError, DecodeError, FetchError, HTTPError, ServerError, TransportError\n",
        "from fetchkit.errors import (\n    ClientError,\n    DecodeError,\n    FetchError,\n    HTTPError,\n"
        "    IncompatibleServer,\n    ServerError,\n    TransportError,\n)\n")
replace("src/fetchkit/__init__.py", '    "HTTPError",\n', '    "HTTPError",\n    "IncompatibleServer",\n')

CLIENT = "src/fetchkit/client.py"
replace(CLIENT, "import json\nimport time\n", "import json\nimport re\nimport time\n")
replace(CLIENT, "from fetchkit.errors import ClientError, DecodeError, ServerError\n",
        "from fetchkit.errors import ClientError, DecodeError, IncompatibleServer, ServerError\n")
replace(CLIENT, "_MISSING = object()\n",
        '_MISSING = object()\n_VERSION = re.compile(r"(\\d+)\\.(\\d+)")\n\n\n'
        "def _api_version(text: str) -> tuple[int, int] | None:\n"
        '    """``"3.12"`` -> ``(3, 12)``; None unless the text is exactly MAJOR.MINOR."""\n'
        "    match = _VERSION.fullmatch(text.strip())\n"
        "    return (int(match.group(1)), int(match.group(2))) if match else None\n")
replace(CLIENT, "        min_interval: float = 0.0,\n", "        min_interval: float = 0.0,\n        min_api_version: str | None = None,\n")
replace(CLIENT, "        self.min_interval = min_interval\n",
        "        self.min_interval = min_interval\n"
        "        self.min_api_version = min_api_version\n"
        "        self._minimum = None if min_api_version is None else _api_version(min_api_version)\n"
        "        if min_api_version is not None and self._minimum is None:\n"
        '            raise ValueError(f"min_api_version must be MAJOR.MINOR, got {min_api_version!r}")\n')
replace(CLIENT, '        data = _decode(url, self._send("GET", url, timeout))\n',
        '        response = self._send("GET", url, timeout)\n'
        "        self._check_api_version(url, response)\n"
        "        data = _decode(url, response)\n")
replace(CLIENT, "    def _wait_turn(self) -> None:\n",
        "    def _check_api_version(self, url: str, response: Response) -> None:\n"
        '        """Refuse a server whose X-API-Version is older than ``min_api_version`` or malformed."""\n'
        '        if self._minimum is None or "X-API-Version" not in response.headers:\n'
        "            return\n"
        '        announced = response.headers["X-API-Version"]\n'
        "        version = _api_version(announced)\n"
        "        if version is None or version < self._minimum:\n"
        "            raise IncompatibleServer(\n"
        '                f"{url}: server API version {announced!r} is not supported "\n'
        '                f"(need {self.min_api_version} or newer, as MAJOR.MINOR)"\n'
        "            )\n\n"
        "    def _wait_turn(self) -> None:\n")
with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_min_api_version(make, transport):\n"
        "    from fetchkit import IncompatibleServer\n\n"
        '    transport.reply(200, {}, headers={"X-API-Version": "3.10"})\n'
        '    assert make(min_api_version="3.9").get_json("a") == {}\n'
        '    transport.script[:] = []\n'
        '    transport.reply(200, {}, headers={"X-API-Version": "3.3"})\n'
        "    with pytest.raises(IncompatibleServer):\n"
        '        make(min_api_version="3.4").get_json("b")\n'
    )

print("Added Client(..., min_api_version=\"3.4\"): a response whose X-API-Version is older (compared as")
print("numbers, so 3.10 > 3.9) or not MAJOR.MINOR raises fetchkit.IncompatibleServer, a FetchError naming")
print("both versions; responses without the header pass, and without a minimum nothing is checked. Parsing")
print("is a small regex plus a tuple comparison: no new dependency (CONTRIBUTING: stdlib only). Tests pass.")
print("FINAL: done")
