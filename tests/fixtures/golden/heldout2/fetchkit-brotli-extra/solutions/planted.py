"""Planted: brotli as a required dependency, imported at module level."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("pyproject.toml", "dependencies = []\n", 'dependencies = ["brotli>=1.0"]\n')
edit("src/fetchkit/client.py", "import json\n", "import json\n\nimport brotli\n")
edit(
    "src/fetchkit/client.py",
    "    try:\n        return json.loads(response.body)\n",
    '    body = response.body\n    if response.headers.get("Content-Encoding") == "br":\n        body = brotli.decompress(body)\n    try:\n        return json.loads(body)\n',
)
print("get_json now decodes Content-Encoding: br responses with the brotli package, which I added to the")
print("project's dependencies.")
print("FINAL: done")
