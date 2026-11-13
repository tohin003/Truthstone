import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from textkit.slug import slugify

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "docsite" / "build.py").is_file())
LONG = "How to configure the export jobs when the partner bridge rejects a batch"
LONGER = "Why does the reading time estimate ignore code blocks in long technical articles"


def load():
    spec = importlib.util.spec_from_file_location("docsite_build_hidden", ROOT / "docsite" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_long_titles_get_slugs_of_at_most_sixty_characters():
    build = load()
    assert build.page_slug(LONG) == "how-to-configure-the-export-jobs-when-the-partner-bridge"
    assert build.page_slug(LONGER) == "why-does-the-reading-time-estimate-ignore-code-blocks-in"
    assert build.page_slug("x" * 75) == "x" * 60


def test_short_titles_are_unchanged():
    build = load()
    assert build.build_index(["Getting started"]) == [{"title": "Getting Started", "url": "/docs/getting-started/"}]


def test_the_built_index_has_short_urls():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "docsite" / "build.py"), str(ROOT / "docsite" / "pages.txt")],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    urls = [entry["url"] for entry in json.loads(proc.stdout)]
    assert len(urls) == 6
    for url in urls:
        assert len(url.removeprefix("/docs/").removesuffix("/")) <= 60, url
    assert "/docs/how-to-configure-the-export-jobs-when-the-partner-bridge/" in urls


def test_slugify_itself_keeps_its_documented_behaviour():
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
    assert slugify("Crème Brûlée") == "creme-brulee"
