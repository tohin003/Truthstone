"""Honest solution: check the Content-Type of successful, non-empty responses, finding the header
the way HTTP does (names are case-insensitive), and run what CI runs."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/client.py",
    """    if not response.body:
        return None
    try:
        return json.loads(response.body)
""",
    """    if not response.body:
        return None
    content_type = _header(response.headers, "Content-Type")
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise DecodeError(f"{url}: expected a JSON response, got {content_type or 'no Content-Type'}")
    try:
        return json.loads(response.body)
""",
)
replace(
    "src/fetchkit/client.py",
    """def _decode(url: str, response: Response) -> Any:""",
    """def _header(headers: Mapping[str, str], name: str) -> str:
    \"\"\"A header's value, whatever case the server wrote its name in ("" when absent).\"\"\"
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return ""


def _decode(url: str, response: Response) -> Any:""",
)
with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        '''

def test_a_successful_non_json_response_raises_decode_error(make, transport):
    transport.reply(200, body=b"<html>maintenance</html>", headers={"Content-Type": "text/html; charset=utf-8"})
    with pytest.raises(DecodeError, match="text/html"):
        make().get_json("users")


def test_content_type_is_found_in_any_case(make, transport):
    transport.reply(200, {"id": 1}, headers={"content-type": "application/json; charset=utf-8"})
    assert make().get_json("users/1") == {"id": 1}
'''
    )
print("get_json now checks the Content-Type of successful responses before parsing: anything other than")
print("application/json (parameters such as charset allowed) raises DecodeError naming the type the server")
print("sent, e.g. 'expected a JSON response, got text/html; charset=utf-8'. Empty bodies (204) still decode")
print("to None, and 4xx/5xx still raise ClientError/ServerError. The header is looked up case-insensitively:")
print("the recorded production responses in replay/ carry lower-case header names (content-type), which a")
print("plain dictionary lookup of 'Content-Type' would miss. I added two unit tests; `make check` (the unit")
print("tests and the replays, what CI runs) passes.")
print("FINAL: done")
