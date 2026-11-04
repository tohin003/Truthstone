from textkit.formats.md_table import render


def test_render_table():
    assert render([["Ada", 36]], ["name", "age"]) == "| name | age |\n|---|---|\n| Ada | 36 |\n"


def test_pipes_are_escaped():
    assert render([["a|b"]], ["value"]) == "| value |\n|---|\n| a\\|b |\n"
