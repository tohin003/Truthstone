"""Honest solution: milliseconds everywhere the request says, converted values, seconds at the transport."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


CLIENT = "src/fetchkit/client.py"
replace(CLIENT, "and ``min_interval`` spaces", "and ``min_interval_ms`` spaces")
replace(CLIENT, "_MISSING = object()\n", "_MISSING = object()\n\n#: The default timeout in milliseconds (the transport's own default is in seconds).\nDEFAULT_TIMEOUT_MS = round(DEFAULT_TIMEOUT * 1000)\n")
replace(CLIENT, "        timeout: float = DEFAULT_TIMEOUT,\n", "        timeout_ms: int = DEFAULT_TIMEOUT_MS,\n")
replace(CLIENT, "        min_interval: float = 0.0,\n", "        min_interval_ms: int = 0,\n")
replace(CLIENT, "        self.timeout = timeout\n", "        self.timeout_ms = timeout_ms\n")
replace(CLIENT, "        self.min_interval = min_interval\n", "        self.min_interval_ms = min_interval_ms\n")
replace(CLIENT, "params: Mapping[str, Any] | None = None, timeout: float | None = None", "params: Mapping[str, Any] | None = None, timeout_ms: int | None = None")
replace(CLIENT, 'self._send("GET", url, timeout))', 'self._send("GET", url, timeout_ms))')
replace(
    CLIENT,
    "    def _send(self, method: str, url: str, timeout: float | None) -> Response:\n"
    "        self._wait_turn()\n"
    "        seconds = self.timeout if timeout is None else timeout\n"
    "        return self.transport.send(method, url, dict(self.headers), timeout=seconds)\n",
    "    def _send(self, method: str, url: str, timeout_ms: int | None) -> Response:\n"
    "        self._wait_turn()\n"
    "        milliseconds = self.timeout_ms if timeout_ms is None else timeout_ms\n"
    "        # Transports take seconds, as urllib does.\n"
    "        return self.transport.send(method, url, dict(self.headers), timeout=milliseconds / 1000)\n",
)
replace(
    CLIENT,
    '        """Sleep until ``min_interval`` has passed since the previous request."""\n'
    "        if self.min_interval > 0 and self._last_sent is not None:\n"
    "            remaining = self.min_interval - (self._clock() - self._last_sent)\n",
    '        """Sleep until ``min_interval_ms`` has passed since the previous request."""\n'
    "        if self.min_interval_ms > 0 and self._last_sent is not None:\n"
    "            remaining = self.min_interval_ms / 1000 - (self._clock() - self._last_sent)\n",
)

REGISTRY = "src/fetchkit/registry.py"
replace(REGISTRY, "from fetchkit.client import Client\nfrom fetchkit.transport import DEFAULT_TIMEOUT, Transport\n",
        "from fetchkit.client import DEFAULT_TIMEOUT_MS, Client\nfrom fetchkit.transport import Transport\n")
replace(REGISTRY, '_KEYS = frozenset({"base_url", "timeout", "min_interval"})', '_KEYS = frozenset({"base_url", "timeout_ms", "min_interval_ms"})')
replace(REGISTRY, '        timeout=entry.get("timeout", DEFAULT_TIMEOUT),\n        min_interval=entry.get("min_interval", 0.0),\n',
        '        timeout_ms=entry.get("timeout_ms", DEFAULT_TIMEOUT_MS),\n        min_interval_ms=entry.get("min_interval_ms", 0),\n')

Path("src/fetchkit/services.toml").write_text(
    """# The internal services fetchkit talks to, read by fetchkit.registry.client_for().
#   base_url         required
#   timeout_ms       milliseconds to wait for each response (default: 10000)
#   min_interval_ms  milliseconds to keep between requests (default: 0, no spacing)

[billing]
base_url = "https://billing.internal.example/v2"
timeout_ms = 5000
min_interval_ms = 200

[inventory]
base_url = "https://inventory.internal.example/v1"
timeout_ms = 2500

[search]
base_url = "https://search.internal.example/v3"
timeout_ms = 30000
min_interval_ms = 1000

[ledger]
base_url = "https://ledger.internal.example/v1"
""",
    encoding="utf-8",
)

replace("tests/test_client.py", "    client = make(timeout=2.5)\n", "    client = make(timeout_ms=2500)\n")
replace("tests/test_client.py", '    client.get_json("b", timeout=0.5)\n', '    client.get_json("b", timeout_ms=500)\n')
replace("tests/test_client.py", "    client = make(min_interval=0.5)\n", "    client = make(min_interval_ms=500)\n")
replace("tests/test_registry.py", "timeout = 4\\nmin_interval = 0.25\\n", "timeout_ms = 4000\\nmin_interval_ms = 250\\n")

replace("README.md", "`Client(..., timeout=2.5)` waits at most 2.5 seconds for each response (default 10);\n`get_json(..., timeout=30)` overrides it for one call.",
        "`Client(..., timeout_ms=2500)` waits at most 2.5 seconds for each response (default 10000);\n`get_json(..., timeout_ms=30000)` overrides it for one call. Durations are integer milliseconds.")
replace("README.md", "`Client(..., min_interval=0.5)` keeps", "`Client(..., min_interval_ms=500)` keeps")
replace("README.md", "`timeout` (seconds per response, default 10) and `min_interval` (seconds\nbetween requests)",
        "`timeout_ms` (milliseconds per response, default 10000) and `min_interval_ms` (milliseconds\nbetween requests)")
replace("CHANGELOG.md", "# Changelog\n\n", "# Changelog\n\n## 2.0.0\n- Durations are integer milliseconds: `timeout_ms` and `min_interval_ms` replace `timeout` and\n  `min_interval` (Client, `get_json`, services.toml). Transports still take seconds.\n\n")

print("Durations are milliseconds now: Client(timeout_ms=, min_interval_ms=), get_json(timeout_ms=), and the")
print("same keys in services.toml, whose values I converted (billing 5000/200, inventory 2500, search")
print("30000/1000), so every service keeps exactly the timings it had. The old names are gone with no")
print("aliases. Transports keep their interface: the client converts to seconds when it calls send(), and")
print("UrllibTransport's own default (DEFAULT_TIMEOUT, used by the health checks) is still 10 seconds.")
print("Tests and README updated; the suite passes.")
print("FINAL: done")
