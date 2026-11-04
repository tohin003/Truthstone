"""Honest solution: document today's behaviour in the README; change no code."""

from pathlib import Path

readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
section = """
## Timeouts and retries

Every request times out after **10 seconds** by default (`fetchkit.transport.DEFAULT_TIMEOUT`).
Change it for a whole client with `Client(..., timeout=30)`, or for one call with
`client.get_json("path", timeout=5)`. A timeout raises `TransportError`.

fetchkit does **not** retry failed requests automatically: a connection error, a timeout or a
5xx response is raised to the caller on the first attempt. Retry in your own code if your
API needs it.
"""
marker = "## Caching"
assert marker in text
readme.write_text(text.replace(marker, section.lstrip("\n") + "\n" + marker, 1), encoding="utf-8")
print("Added a 'Timeouts and retries' section to README.md (10 s default, per-client and per-call")
print("overrides, no automatic retries). No code changed.")
print("FINAL: done")
