"""textkit.legacy_case is now textkit.compat, and everything that used it still works."""

import importlib
import importlib.util
import tomllib
from pathlib import Path

import pytest

import textkit
from textkit.cli import main
from textkit.keys import rename_keys

ROOT = Path(__file__).resolve().parents[2]


def test_compat_has_the_0x_helpers_with_their_old_behaviour():
    compat = importlib.import_module("textkit.compat")
    assert compat.underscore("parseHTTPResponse") == "parse_httpresponse"
    assert compat.underscore("Hello World-Again") == "hello_world_again"
    assert compat.dasherize("Hello_World again") == "Hello-World-again"
    assert compat.camelize("hello_world") == "HelloWorld"
    assert compat.camelize("hello_world", upper_first=False) == "helloWorld"
    assert compat.humanize("created_at") == "Created at"


def test_no_legacy_case_module_is_left():
    assert importlib.util.find_spec("textkit.legacy_case") is None
    assert not (ROOT / "src" / "textkit" / "legacy_case.py").exists()


def test_the_0x_top_level_names_still_work():
    assert textkit.camelize("hello_world") == "HelloWorld"
    assert textkit.underscore("createdAt") == "created_at"
    assert textkit.dasherize("Hello_World") == "Hello-World"
    assert textkit.humanize("updated_by") == "Updated by"
    with pytest.raises(AttributeError):
        textkit.no_such_helper  # noqa: B018


def test_the_labels_command(capsys):
    assert main(["labels", "created_at", "updated_by"]) == 0
    assert capsys.readouterr().out == "Created at\nUpdated by\n"


def test_the_human_style(capsys):
    assert main(["case", "--style", "human", "created_at"]) == 0
    assert capsys.readouterr().out == "Created at\n"


def test_the_key_renamer():
    assert rename_keys({"createdAt": 1, "owner": {"displayName": "Ada"}}) == {
        "created_at": 1,
        "owner": {"display_name": "Ada"},
    }
    assert rename_keys({"created_at": 1}, "camel") == {"createdAt": 1}
    assert rename_keys({"created_at": 1}, "pascal") == {"CreatedAt": 1}


def docs_site_filters():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["entry-points"]["docsite.filters"]


def resolve(spec):
    module, _, attribute = spec.partition(":")
    return getattr(importlib.import_module(module), attribute)


def test_every_docs_site_filter_still_resolves():
    filters = docs_site_filters()
    assert set(filters) == {"slugify", "title", "label", "reading_time"}
    for name, spec in filters.items():
        assert callable(resolve(spec)), name
    assert resolve(filters["label"])("created_at") == "Created at"
    assert resolve(filters["title"])("war and peace") == "War and Peace"


def test_the_readme_names_the_new_module():
    assert "textkit.compat" in (ROOT / "README.md").read_text(encoding="utf-8")
