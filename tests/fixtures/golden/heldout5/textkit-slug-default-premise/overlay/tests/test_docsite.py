import importlib.util
from pathlib import Path

# the repository root: the first parent that holds docsite/
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "docsite" / "build.py").is_file())
_spec = importlib.util.spec_from_file_location("docsite_build", ROOT / "docsite" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def test_index_entries():
    assert build.build_index(["getting started", "the slug module"]) == [
        {"title": "Getting Started", "url": "/docs/getting-started/"},
        {"title": "The Slug Module", "url": "/docs/the-slug-module/"},
    ]
