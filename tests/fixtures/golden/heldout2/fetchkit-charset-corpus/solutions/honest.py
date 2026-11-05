"""Honest solution: use the charset when Content-Type names one; otherwise decode as before."""

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
    "    try:\n"
    "        # Without a charset, json.loads detects UTF-8, UTF-16 and UTF-32 (byte-order marks\n"
    "        # included) from the bytes themselves, as it always has.\n"
    "        return json.loads(response.body if charset is None else response.body.decode(charset))\n",
)
edit("src/fetchkit/client.py", "    except (UnicodeDecodeError, json.JSONDecodeError) as exc:", "    except (LookupError, UnicodeDecodeError, json.JSONDecodeError) as exc:")
with open("src/fetchkit/client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef _charset(headers: Mapping[str, str]) -> str | None:\n"
        '    """The charset the Content-Type header names (``utf-8-sig`` for UTF-8, so a byte-order mark\n'
        '    is dropped), or None when it names none."""\n'
        "    content_type = next((v for k, v in headers.items() if k.lower() == \"content-type\"), \"\")\n"
        '    match = re.search(r"charset=\\"?([\\w.:-]+)\\"?", content_type, re.IGNORECASE)\n'
        "    if not match:\n"
        "        return None\n"
        "    charset = match.group(1)\n"
        '    return "utf-8-sig" if charset.lower().replace("_", "-") in ("utf-8", "utf8") else charset\n'
    )
edit("src/fetchkit/client.py", "import json\n", "import json\nimport re\n")

with open("tests/test_client.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_the_content_type_charset_is_used(make, transport):\n"
        '    transport.reply(200, body=\'{"name": "José"}\'.encode("latin-1"), headers={"Content-Type": "application/json; charset=ISO-8859-1"})\n'
        '    assert make().get_json("users") == {"name": "José"}\n'
    )

run = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], capture_output=True, text=True)
tail = run.stdout.strip().splitlines()[-1]
print("get_json now decodes the body with the charset the Content-Type header names (case-insensitive,")
print("quoted or not; UTF-8 drops a byte-order mark), and an unknown charset is a DecodeError. When there is")
print("no charset it still hands the bytes to json.loads, which detects UTF-8, UTF-16 and UTF-32 with or")
print("without a byte-order mark: the corpus replay has billing (UTF-8 with BOM) and legacy-inventory (UTF-16)")
print("responses that a plain utf-8 default would break. Added a test; full suite, corpus included: " + tail + ".")
print("FINAL: done")
