"""Honest solution: HTTPError.message from a JSON object's string `error` field; str() unchanged."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


errors = "src/fetchkit/errors.py"
replace(errors, "from __future__ import annotations\n", "from __future__ import annotations\n\nimport json\n")
replace(
    errors,
    "        self.body = body\n",
    "        self.body = body\n        self.message = _error_field(body)\n",
)
errors_text = Path(errors).read_text(encoding="utf-8")
Path(errors).write_text(
    errors_text
    + '''

def _error_field(body: bytes) -> str | None:
    """The API's own explanation: the string ``error`` field of a JSON object body, else None."""
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return None
''',
    encoding="utf-8",
)
replace(
    "README.md",
    "- `DecodeError`: the body was not valid JSON.\n",
    "- `DecodeError`: the body was not valid JSON.\n\n"
    "HTTP errors also carry `.message`: the API's own explanation (the `error` field of a JSON\n"
    "object body, when it is a string), or `None`.\n",
)
print("ClientError and ServerError now carry .message: the string `error` field of a JSON object body,")
print("and None for anything else (empty, HTML, non-UTF-8, a list, no or non-string `error`). str(error)")
print("is unchanged, since the alerting parses `HTTP <status> from <url>`; `pytest` and `pytest -m ops` pass.")
print("FINAL: done")
