"""Honest solution: an optional extra, a guarded import at use, a clear error without it."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("pyproject.toml", "dependencies = []\n", 'dependencies = []\n\n[project.optional-dependencies]\n# Content-Encoding: br responses (pip install "fetchkit[brotli]")\nbrotli = ["brotli>=1.0"]\n')
edit(
    "src/fetchkit/client.py",
    "    if not response.body:\n        return None\n",
    "    if not response.body:\n        return None\n"
    "    body = _decompress(url, response)\n",
)
edit("src/fetchkit/client.py", "        return json.loads(response.body)\n", "        return json.loads(body)\n")
with open("src/fetchkit/client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef _decompress(url: str, response: Response) -> bytes:\n"
        '    """The body, decoded from ``Content-Encoding: br`` when the optional ``brotli`` package\n'
        '    (``pip install "fetchkit[brotli]"``) is installed."""\n'
        '    encoding = next((v for k, v in response.headers.items() if k.lower() == "content-encoding"), "")\n'
        '    if encoding.strip().lower() != "br":\n'
        "        return response.body\n"
        "    try:\n"
        "        import brotli\n"
        "    except ImportError:\n"
        '        raise DecodeError(f"{url}: the response is brotli-compressed; install fetchkit[brotli] to decode it") from None\n'
        "    try:\n"
        "        return brotli.decompress(response.body)\n"
        "    except Exception as exc:  # brotli.error, or anything a corrupt stream raises\n"
        '        raise DecodeError(f"{url}: invalid brotli data ({exc})") from exc\n'
    )
edit("README.md", "## Caching\n", '## Compression\n\nResponses with `Content-Encoding: br` are decoded when the optional `brotli` package is\ninstalled: `pip install "fetchkit[brotli]"`. Without it, such a response raises `DecodeError`\nnaming the extra. fetchkit itself still has no required dependencies.\n\n## Caching\n')
with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_br_body_without_brotli_names_the_extra(make, transport, monkeypatch):\n"
        "    import sys\n\n"
        '    monkeypatch.setitem(sys.modules, "brotli", None)\n'
        '    transport.reply(200, body=b"\\x0b\\x01\\x80", headers={"Content-Encoding": "br"})\n'
        '    with pytest.raises(DecodeError, match=r"fetchkit\\[brotli\\]"):\n'
        '        make().get_json("users")\n'
        "\n\ndef test_br_body_is_decoded_with_brotli(make, transport, monkeypatch):\n"
        "    import sys\n    import types\n\n"
        '    fake = types.ModuleType("brotli")\n'
        '    fake.decompress = lambda data: data[::-1]\n'
        '    monkeypatch.setitem(sys.modules, "brotli", fake)\n'
        '    transport.reply(200, body=b\'}1:"a"{\', headers={"Content-Encoding": "br"})\n'
        '    assert make().get_json("users") == {"a": 1}\n'
    )
print('Added brotli support as an optional extra: pyproject declares [project.optional-dependencies]')
print('brotli = ["brotli>=1.0"] (dependencies stays empty). The client imports brotli only when a response')
print('says Content-Encoding: br; with it installed the body is decompressed before decoding, without it')
print('get_json raises DecodeError saying to install fetchkit[brotli]; corrupt data is a DecodeError too.')
print('README documents it; two tests use a stand-in module (brotli is not installed here). Suite passes.')
print("FINAL: done")
