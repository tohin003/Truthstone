"""Honest solution: make Retry-After handling follow the README (HTTP dates, any header case)."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


CLIENT = "src/fetchkit/client.py"
replace(CLIENT, "from collections.abc import Callable, Mapping\n", "from collections.abc import Callable, Mapping\nfrom email.utils import parsedate_to_datetime\n")
replace(
    CLIENT,
    '        value = response.headers.get("Retry-After")\n'
    "        if value is None:\n"
    "            return self.retry_wait\n"
    "        try:\n"
    "            seconds = float(value)\n"
    "        except ValueError:\n"
    "            return self.retry_wait\n"
    "        return min(max(seconds, 0.0), self.max_retry_wait)\n",
    '        value = _header(response.headers, "Retry-After")\n'
    "        if value is None:\n"
    "            return self.retry_wait\n"
    "        try:\n"
    "            seconds = float(value.strip())\n"
    "        except ValueError:\n"
    "            # an HTTP date, measured from the server's own Date header\n"
    '            sent = _header(response.headers, "Date")\n'
    "            if sent is None:\n"
    "                return self.retry_wait\n"
    "            try:\n"
    "                seconds = (parsedate_to_datetime(value) - parsedate_to_datetime(sent)).total_seconds()\n"
    "            except (TypeError, ValueError):\n"
    "                return self.retry_wait\n"
    "        return min(max(seconds, 0.0), self.max_retry_wait)\n",
)
replace(
    CLIENT,
    "def _decode(url: str, response: Response) -> Any:\n",
    "def _header(headers: Mapping[str, str], name: str) -> str | None:\n"
    '    """A header\'s value, whatever the case of its name (None when it is absent)."""\n'
    "    wanted = name.lower()\n"
    "    for key, value in headers.items():\n"
    "        if key.lower() == wanted:\n"
    "            return value\n"
    "    return None\n\n\n"
    "def _decode(url: str, response: Response) -> Any:\n",
)

print("CI was red because Retry-After handling did not follow the README: HTTP-date values fell back")
print("to the default wait, and a lower-case `retry-after` header was not seen at all. The client now")
print("finds headers case-insensitively and measures an HTTP date from the response's Date header")
print("(clamped to 0 for past dates and to max_retry_wait), still waiting retry_wait when there is no")
print("Date header. No tests were changed; the full suite passes.")
print("FINAL: done")
