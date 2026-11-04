"""RFC 4180 quoting for the CSV formatter; its existing output is otherwise unchanged."""

import csv
import io

from textkit.formats.csv_fmt import render


def parse(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def test_embedded_quotes_are_doubled_inside_a_quoted_field():
    assert render([['say "hi"', "ok"]], ["quote", "status"]) == 'quote,status\n"say ""hi""",ok\n'


def test_line_breaks_are_quoted():
    assert render([["line one\nline two"]], ["note"]) == 'note\n"line one\nline two"\n'
    assert render([["a\rb"]], ["note"]) == 'note\n"a\rb"\n'


def test_comma_and_quotes_together():
    assert render([['Lovelace, "Ada"']], ["name"]) == 'name\n"Lovelace, ""Ada"""\n'


def test_headers_follow_the_same_rule():
    assert render([[1]], ['size "cm"']) == '"size ""cm"""\n1\n'


def test_plain_values_are_unchanged():
    assert render([["Ada", 36, None, 1.5]], ["name", "age", "team", "score"]) == (
        "name,age,team,score\nAda,36,,1.5\n"
    )
    assert render([["Lovelace, Ada"]], ["name"]) == 'name\n"Lovelace, Ada"\n'


def test_output_round_trips_through_a_csv_reader():
    headers = ["a", "b", "c", "d"]
    row = ["Lovelace, Ada", 'say "hi"', "two\nlines", "plain"]
    assert parse(render([row], headers)) == [headers, row]
