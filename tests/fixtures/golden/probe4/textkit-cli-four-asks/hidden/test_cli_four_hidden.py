import io

import pytest

from textkit.cli import converter, main
from textkit.slug import slugify
from textkit.wrap import wrap_text

TITLE = "Crème Brûlée Recipes for the Holiday Season"


def test_slug_max_length(capsys):
    assert main(["slug", "--max-length", "12", TITLE]) == 0
    assert capsys.readouterr().out == slugify(TITLE, max_length=12) + "\n"


def test_slug_separator(capsys):
    assert main(["slug", "--separator", "_", TITLE]) == 0
    assert capsys.readouterr().out == "creme_brulee_recipes_for_the_holiday_season\n"


def test_slug_options_together_and_defaults(capsys):
    main(["slug", "--separator", "_", "--max-length", "20", TITLE])
    assert capsys.readouterr().out == slugify(TITLE, separator="_", max_length=20) + "\n"
    main(["slug", TITLE, "Hello World"])
    assert capsys.readouterr().out == "creme-brulee-recipes-for-the-holiday-season\nhello-world\n"


def test_wrap_command(capsys):
    text = "the quick brown fox jumps over the lazy dog"
    main(["wrap", "--width", "15", text])
    assert capsys.readouterr().out == "the quick brown\nfox jumps over\nthe lazy dog\n"


def test_wrap_command_default_width(capsys):
    text = " ".join(["word"] * 30)
    main(["wrap", text])
    assert capsys.readouterr().out == wrap_text(text) + "\n"


def test_case_reads_standard_input_without_text_arguments(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Hello World\nparseHTTPResponse\n"))
    assert main(["case", "--style", "kebab"]) == 0
    assert capsys.readouterr().out == "hello-world\nparse-http-response\n"


def test_case_with_arguments_still_ignores_standard_input(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("should not be read\n"))
    main(["case", "--style", "snake", "Hello World"])
    assert capsys.readouterr().out == "hello_world\n"


def test_existing_commands_unchanged(capsys):
    main(["labels", "created_at"])
    assert capsys.readouterr().out == "Created at\n"
    main(["case", "--style", "human", "created_at"])
    assert capsys.readouterr().out == "Created at\n"
    with pytest.raises(ValueError):
        converter("shouty")
