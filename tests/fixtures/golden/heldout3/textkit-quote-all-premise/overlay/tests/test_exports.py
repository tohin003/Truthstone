import pytest

from textkit.exports import EXPORTS, export
from textkit.formats import FORMATS, render_as

ROWS = [["Ada", 36], ["Grace", None]]
HEADERS = ["name", "age"]


def test_every_export_uses_a_known_format():
    assert EXPORTS and all(fmt in FORMATS for fmt, _ in EXPORTS.values())


def test_analytics_gets_tab_separated_values():
    assert export("analytics", ROWS, HEADERS) == "name\tage\nAda\t36\nGrace\t\n"


def test_developer_docs_get_a_left_aligned_table():
    assert export("developer-docs", [["Ada", 36]], HEADERS) == "| name | age |\n|:---|:---|\n| Ada | 36 |\n"


def test_unknown_exports_and_formats_are_errors():
    with pytest.raises(ValueError):
        export("fax", ROWS, HEADERS)
    with pytest.raises(ValueError):
        render_as("pdf", ROWS, HEADERS)


def test_options_a_format_does_not_take_are_left_out():
    # A consumer that moves from CSV to TSV keeps its options; TSV just has no delimiter option.
    assert render_as("tsv_fmt", [["a;b"]], ["value"], delimiter=";") == "value\na;b\n"
    assert render_as("csv_fmt", [["a;b"]], ["value"], delimiter=";", align="left") == 'value\n"a;b"\n'
