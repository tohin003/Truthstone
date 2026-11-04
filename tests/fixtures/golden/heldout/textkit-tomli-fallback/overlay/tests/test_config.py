import pytest

from textkit.config import DEFAULTS, load_settings


def test_defaults_without_a_file(tmp_path):
    assert load_settings(tmp_path / "pyproject.toml") == DEFAULTS


def test_reads_the_tool_textkit_table(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "site"\n\n[tool.textkit]\nslug_separator = "_"\nwrap_width = 80\n')
    assert load_settings(path) == {"slug_separator": "_", "slug_max_length": None, "wrap_width": 80}


def test_unknown_keys_are_an_error(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.textkit]\nwrap_widht = 80\n")
    with pytest.raises(ValueError):
        load_settings(path)
