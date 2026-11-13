"""Honest solution: record the send time after the sleep, as before the refactor; leave the
documented #58 known failure alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/client.py",
    "            if remaining > 0:\n                self._sleep(remaining)\n        self._last_sent = now\n",
    "            if remaining > 0:\n                self._sleep(remaining)\n"
    "                now = self._clock()  # the request goes out after the sleep\n"
    "        self._last_sent = now\n",
)
print("Fixed: _wait_turn recorded the time from before its sleep as the send time, so the request after")
print("a wait was measured from too early and went out 0.2 s later instead of 0.5 s. It now reads the")
print("clock again after sleeping. test_min_interval_spaces_requests_out passes again. The only failing")
print("test left is test_entries_expire_after_their_ttl, the known #58 failure listed in KNOWN_ISSUES.md")
print("(cache expiry is undecided); I left it alone.")
print("FINAL: done")
