"""Builds the docs site's page index: every page title gets a URL under /docs/.

    PYTHONPATH=src python docsite/build.py docsite/pages.txt > docsite/index.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from textkit import slug
from textkit.case import title_case


def page_slug(title: str) -> str:
    return slug.slugify(title)


def build_index(titles: list[str]) -> list[dict[str, str]]:
    return [{"title": title_case(title), "url": f"/docs/{page_slug(title)}/"} for title in titles]


def main(argv: list[str]) -> int:
    lines = Path(argv[0]).read_text(encoding="utf-8").splitlines()
    json.dump(build_index([line.strip() for line in lines if line.strip()]), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
