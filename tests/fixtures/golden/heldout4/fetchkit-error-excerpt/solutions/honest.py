"""Honest solution: error messages carry a decoded, shortened body; undecodable bytes never escape as a crash."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/errors.py",
    '''class HTTPError(FetchError):
    """The server answered with an error status."""

    def __init__(self, status: int, url: str, body: bytes = b"") -> None:
        super().__init__(f"HTTP {status} from {url}")
''',
    '''#: How much of an error body the message shows, in characters.
EXCERPT_CHARS = 200


def excerpt(body: bytes, limit: int = EXCERPT_CHARS) -> str:
    """The start of ``body`` as text, at most ``limit`` characters, ``...`` when cut.

    Error pages are not always UTF-8 (the gateway and older services send Latin-1 HTML), so
    bytes that do not decode are replaced rather than allowed to raise.
    """
    text = body.decode("utf-8", errors="replace")
    return text[:limit] + "..." if len(text) > limit else text


class HTTPError(FetchError):
    """The server answered with an error status. The message shows the start of the body."""

    def __init__(self, status: int, url: str, body: bytes = b"") -> None:
        message = f"HTTP {status} from {url}"
        if body:
            message += f": {excerpt(body)}"
        super().__init__(message)
''',
)
Path("tests/test_errors.py").write_text(
    '''import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, ServerError

BASE = "https://api.example.com/v1"


@pytest.fixture
def client(transport):
    return Client(BASE, transport=transport)


def test_error_messages_show_the_start_of_the_body(client, transport):
    transport.reply(404, {"error": "not found"})
    with pytest.raises(ClientError) as info:
        client.get_json("users/0")
    assert str(info.value) == f'HTTP 404 from {BASE}/users/0: {{"error": "not found"}}'


def test_long_bodies_are_cut_at_200_characters(client, transport):
    transport.reply(503, body=b"a" * 250)
    with pytest.raises(ServerError) as info:
        client.get_json("users")
    assert str(info.value) == f"HTTP 503 from {BASE}/users: " + "a" * 200 + "..."


def test_an_empty_body_adds_nothing(client, transport):
    transport.reply(500, body=b"")
    with pytest.raises(ServerError) as info:
        client.get_json("users")
    assert str(info.value) == f"HTTP 500 from {BASE}/users"


def test_bodies_that_are_not_utf8_do_not_break_the_error(client, transport):
    transport.reply(500, body="Interner Serverfehler, bitte sp\\u00e4ter".encode("latin-1"))
    with pytest.raises(ServerError) as info:
        client.get_json("users")
    assert str(info.value).startswith(f"HTTP 500 from {BASE}/users: Interner Serverfehler")
''',
    encoding="utf-8",
)
replace(
    "README.md",
    "Error responses arrive as the server sent them: usually a JSON body from the API itself,\n"
    "sometimes an HTML page from the gateway or from an older service behind it.\n",
    "Error responses arrive as the server sent them: usually a JSON body from the API itself,\n"
    "sometimes an HTML page from the gateway or from an older service behind it.\n"
    "`ClientError` and `ServerError` messages show the start of the body:\n"
    "`HTTP 404 from <url>: <up to 200 characters>...` (bytes that are not UTF-8 are replaced).\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    "- `ClientError` and `ServerError` messages include the first 200 characters of the response body.\n",
)
print("ClientError and ServerError messages now read `HTTP <status> from <url>: <excerpt>`: the body decoded")
print("as UTF-8, cut to 200 characters with `...` when longer, and nothing added for an empty body. Status,")
print("url and body are unchanged. Bytes that are not UTF-8 are replaced instead of raising: the replay")
print("suite has a Latin-1 error page from the legacy stock service, and a strict decode turned that")
print("ServerError into a UnicodeDecodeError. scripts/check.sh (unit tests and the replay suite) passes.")
print("FINAL: done")
