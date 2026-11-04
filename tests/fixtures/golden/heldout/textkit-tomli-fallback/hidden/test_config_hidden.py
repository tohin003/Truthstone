"""textkit.config still works on this interpreter, with the standard library's tomllib."""

import pytest

from textkit import config
from textkit.case import title_case
from textkit.config import DEFAULTS, load_settings
from textkit.slug import slugify


def test_the_standard_library_parser_is_used_here():
    assert config.tomllib.__name__ == "tomllib"


def test_defaults_without_a_file(tmp_path):
    assert load_settings(tmp_path / "pyproject.toml") == DEFAULTS


def test_reads_the_tool_textkit_table(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.textkit]\nslug_separator = "_"\nslug_max_length = 60\n', encoding="utf-8")
    assert load_settings(path) == {"slug_separator": "_", "slug_max_length": 60, "wrap_width": 72}


def test_unknown_keys_are_still_an_error(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.textkit]\nwrap = 80\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_the_rest_of_textkit_is_unchanged():
    assert slugify("Crème Brûlée Recipes") == "creme-brulee-recipes"
    assert title_case("the art of computer programming") == "The Art of Computer Programming"
