import pytest

from textkit.cli import converter, main


def test_case_command(capsys):
    assert main(["case", "--style", "kebab", "Hello World", "parseHTTPResponse"]) == 0
    assert capsys.readouterr().out == "hello-world\nparse-http-response\n"


def test_human_style(capsys):
    main(["case", "--style", "human", "created_at"])
    assert capsys.readouterr().out == "Created at\n"


def test_slug_command_and_unknown_style(capsys):
    main(["slug", "Crème Brûlée"])
    assert capsys.readouterr().out == "creme-brulee\n"
    with pytest.raises(ValueError):
        converter("shouty")


def test_slug_command_max_length(capsys):
    # Product names can be a single long word (brand names, German compounds); they still
    # get a slug of at most --max-length characters.
    assert main(["slug", "--max-length", "12", "Crème Brûlée", "Donaudampfschifffahrt"]) == 0
    assert capsys.readouterr().out == "creme-brulee\ndonaudampfsc\n"
