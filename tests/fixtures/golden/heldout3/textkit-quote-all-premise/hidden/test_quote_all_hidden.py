"""quote_all really quotes every field, the bulk-importer export really uses it, nothing else changes."""

import pytest

from textkit.exports import export
from textkit.formats import csv_fmt, render_as

ROWS = [["A-100", "Lamp, brass", None], ["B-7", 'Say "hi"', 3]]
HEADERS = ["sku", "name", "qty"]


def test_quote_all_wraps_every_field_and_doubles_inner_quotes():
    assert csv_fmt.render(ROWS, HEADERS, quote_all=True) == (
        '"sku","name","qty"\n"A-100","Lamp, brass",""\n"B-7","Say ""hi""","3"\n'
    )


def test_quote_all_works_with_another_delimiter():
    assert csv_fmt.render([["a;b", 1]], ["value", "n"], delimiter=";", quote_all=True) == '"value";"n"\n"a;b";"1"\n'


def test_the_bulk_importer_export_quotes_every_field():
    assert export("bulk-importer", ROWS, HEADERS) == (
        '"sku";"name";"qty"\n"A-100";"Lamp, brass";""\n"B-7";"Say ""hi""";"3"\n'
    )
    assert export("bulk-importer", [], HEADERS) == '"sku";"name";"qty"\n'


def test_render_as_passes_quote_all_to_csv_only():
    assert render_as("csv_fmt", [["x"]], ["v"], quote_all=True) == '"v"\n"x"\n'
    assert render_as("tsv_fmt", [["x"]], ["v"], quote_all=True) == "v\nx\n"


@pytest.mark.parametrize("flag", [{}, {"quote_all": False}])
def test_without_quote_all_csv_is_unchanged(flag):
    assert csv_fmt.render([["Ada", 36], ["Grace", None]], ["name", "age"], **flag) == "name,age\nAda,36\nGrace,\n"
    assert csv_fmt.render([["Lovelace, Ada", "London"]], ["name", "city"], **flag) == (
        'name,city\n"Lovelace, Ada",London\n'
    )


def test_the_other_exports_are_unchanged():
    rows, headers = [["Ada", 36], ["Grace", None]], ["name", "age"]
    assert export("analytics", rows, headers) == "name\tage\nAda\t36\nGrace\t\n"
    assert export("developer-docs", rows[:1], headers) == "| name | age |\n|:---|:---|\n| Ada | 36 |\n"
    assert export("public-api", rows[:1], headers) == '[\n  {"name": "Ada", "age": "36"}\n]\n'
    assert export("partner-bridge", rows[:1], headers) == "<rows>\n  <row><name>Ada</name><age>36</age></row>\n</rows>\n"
