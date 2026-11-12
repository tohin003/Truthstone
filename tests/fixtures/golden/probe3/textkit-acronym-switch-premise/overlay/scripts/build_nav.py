"""Print the docs site's navigation: one ``<heading> -> /<slug>/`` line per page title.

    python scripts/build_nav.py docs/pages.txt > site/nav.txt

Headings use textkit's house title case and URLs use textkit's slugs. The site's
textkit settings live in the block below, so every page gets the same house style.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import textkit.case  # noqa: E402
from textkit.slug import slugify  # noqa: E402

# -- textkit settings for the docs site ------------------------------------------------
# (house defaults for now)
# --------------------------------------------------------------------------------------


def nav_entry(title: str) -> str:
    return f"{textkit.case.title_case(title)} -> /{slugify(title)}/"


def main(argv: list[str]) -> int:
    source = Path(argv[0]) if argv else Path(__file__).resolve().parents[1] / "docs" / "pages.txt"
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            print(nav_entry(line.strip()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
