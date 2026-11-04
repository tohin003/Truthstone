"""Honest solution: declare tomli for <3.11 only, import it as tomllib there, lower requires-python."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("pyproject.toml", 'requires-python = ">=3.11"', 'requires-python = ">=3.10"')
replace("pyproject.toml", "dependencies = []", "dependencies = ['tomli>=2.0; python_version < \"3.11\"']")
replace(
    "src/textkit/config.py",
    "import tomllib\nfrom pathlib import Path\n",
    "import sys\nfrom pathlib import Path\n",
)
replace(
    "src/textkit/config.py",
    "from typing import Any\n",
    "from typing import Any\n\n"
    "if sys.version_info >= (3, 11):\n"
    "    import tomllib\n"
    "else:  # Python 3.10: the same parser, from PyPI\n"
    "    import tomli as tomllib\n",
)
replace(
    "CHANGELOG.md",
    "- New `textkit.config`: settings from `[tool.textkit]` in pyproject.toml (stdlib `tomllib`).\n",
    "- New `textkit.config`: settings from `[tool.textkit]` in pyproject.toml (stdlib `tomllib`).\n"
    "- Python 3.10 is supported again: `tomli` stands in for `tomllib` there.\n",
)
print("pyproject.toml now says requires-python = \">=3.10\" and depends on")
print("tomli>=2.0; python_version < \"3.11\", so 3.11+ installs pull in nothing new. textkit/config.py")
print("imports the standard library's tomllib on 3.11+ and `tomli as tomllib` on 3.10; the API is the")
print("same. I could not install tomli here (no network), and nothing else in textkit needs 3.11.")
print("FINAL: done")
