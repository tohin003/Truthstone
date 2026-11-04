"""Newlines inside Markdown table cells render as <br>; everything else about the table is unchanged."""

from textkit.formats.md_table import render


def test_a_newline_inside_a_cell_becomes_br():
    assert render([["line one\nline two", "x"]], ["note", "id"]) == (
        "| note | id |\n|---|---|\n| line one<br>line two | x |\n"
    )


def test_windows_newlines_too():
    assert render([["a\r\nb"]], ["v"]) == "| v |\n|---|\n| a<br>b |\n"


def test_pipes_none_and_plain_values_are_unchanged():
    assert render([["a|b\nc", None, 3]], ["v", "w", "n"]) == "| v | w | n |\n|---|---|---|\n| a\\|b<br>c |  | 3 |\n"
    assert render([["Ada", 36]], ["name", "age"]) == "| name | age |\n|---|---|\n| Ada | 36 |\n"


def test_each_row_stays_on_one_line():
    text = render([["one\ntwo\nthree", "x"], ["four", "y\nz"]], ["a", "b"])
    assert text.count("\n") == 4
