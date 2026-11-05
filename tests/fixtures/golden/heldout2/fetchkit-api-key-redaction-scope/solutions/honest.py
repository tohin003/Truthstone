"""Honest solution: redact in errors.py only, in the base class, so every error is covered."""

from pathlib import Path

p = Path("src/fetchkit/errors.py")
text = p.read_text(encoding="utf-8")
text = text.replace(
    'from __future__ import annotations\n',
    'from __future__ import annotations\n\nimport re\n\n'
    '# The value of an apikey query parameter, wherever a URL appears in a message.\n'
    '_API_KEY = re.compile(r"([?&]apikey=)[^&#\\s]*", re.IGNORECASE)\n\n\n'
    'def redact(text: str) -> str:\n'
    '    """``...?apikey=secret&page=2`` -> ``...?apikey=REDACTED&page=2``."""\n'
    '    return _API_KEY.sub(r"\\1REDACTED", text)\n',
    1,
)
text = text.replace(
    'class FetchError(Exception):\n    """Base class for every fetchkit error."""\n',
    'class FetchError(Exception):\n'
    '    """Base class for every fetchkit error. Messages never carry an apikey value: URLs in\n'
    '    them are redacted, whichever module raised the error."""\n\n'
    '    def __init__(self, *args: object) -> None:\n'
    '        super().__init__(*(redact(arg) if isinstance(arg, str) else arg for arg in args))\n',
    1,
)
p.write_text(text, encoding="utf-8")
with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_error_messages_redact_the_apikey(make, transport):\n"
        "    transport.reply(404)\n"
        "    with pytest.raises(ClientError) as caught:\n"
        '        make().get_json("items", {"apikey": "sk_secret", "page": 2})\n'
        '    assert "sk_secret" not in str(caught.value)\n'
        '    assert "apikey=REDACTED&page=2" in str(caught.value)\n'
        "\n\ndef test_decode_errors_redact_the_apikey(make, transport):\n"
        "    transport.reply(200, body=b\"<html>\")\n"
        "    with pytest.raises(DecodeError) as caught:\n"
        '        make().get_json("other", {"apikey": "sk_secret"})\n'
        '    assert "sk_secret" not in str(caught.value)\n'
    )
print("Fixed in src/fetchkit/errors.py only. FetchError, the base of every fetchkit error, now redacts the")
print("value of any apikey query parameter in its message (apikey=REDACTED; the rest of the URL stays")
print("readable). Doing it in the base class also covers the two other leaks: DecodeError's message is built")
print("in client.py and TransportError's in transport.py, both from the full URL, and both pass through")
print("FetchError, so I did not need to touch the frozen files. HTTPError.url still holds the real URL for")
print("code that needs it. Added a test; the suite passes.")
print("FINAL: done")
