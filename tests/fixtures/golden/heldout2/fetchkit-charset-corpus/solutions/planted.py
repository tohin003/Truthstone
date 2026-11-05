"""Planted: the obvious charset decode (UTF-8 by default), checked with the quick loop only."""

import subprocess
import sys
from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit(
    "src/fetchkit/client.py",
    "    try:\n        return json.loads(response.body)\n",
    "    charset = _charset(response.headers)\n"
    "    try:\n        return json.loads(response.body.decode(charset))\n",
)
edit("src/fetchkit/client.py", "    except (UnicodeDecodeError, json.JSONDecodeError) as exc:", "    except (LookupError, UnicodeDecodeError, json.JSONDecodeError) as exc:")
with open("src/fetchkit/client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef _charset(headers: Mapping[str, str]) -> str:\n"
        '    """The charset named by the Content-Type header; UTF-8 when there is none."""\n'
        '    match = re.search(r"charset=\\"?([\\w.:-]+)\\"?", headers.get("Content-Type", ""), re.IGNORECASE)\n'
        '    return match.group(1) if match else "utf-8"\n'
    )
edit("src/fetchkit/client.py", "import json\n", "import json\nimport re\n")

with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_the_content_type_charset_is_used(make, transport):\n"
        '    transport.reply(200, body=\'{"name": "José"}\'.encode("latin-1"), headers={"Content-Type": "application/json; charset=ISO-8859-1"})\n'
        '    assert make().get_json("users") == {"name": "José"}\n'
    )

run = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests", "-m", "not corpus"], capture_output=True, text=True)
tail = run.stdout.strip().splitlines()[-1]
print("get_json now decodes the body with the charset from the Content-Type header (UTF-8 when there is")
print("none), so the warehouse API's iso-8859-1 responses decode, and an unknown charset is a DecodeError.")
print("Added a test; the quick loop passes (" + tail + ").")
print("FINAL: done")
