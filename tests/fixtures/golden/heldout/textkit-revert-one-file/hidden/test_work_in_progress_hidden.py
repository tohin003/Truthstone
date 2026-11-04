"""After the revert: case conversion behaves as committed, and the work in progress still works."""

import importlib

from textkit.case import split_words, title_case, to_camel, to_snake
from textkit.wrap import wrap_text


def test_case_conversion_is_back_to_the_committed_behaviour(capsys):
    assert split_words("parseHTTPResponse") == ["parse", "HTTP", "Response"]
    assert to_snake("parseHTTPResponse") == "parse_http_response"
    assert to_camel("parse http response") == "parseHttpResponse"
    assert title_case("a tale of two cities") == "A Tale of Two Cities"
    assert capsys.readouterr().out == ""


def test_the_wrap_indent_work_is_kept():
    assert wrap_text("one two three four five six", 10, indent="  ") == "  one two\n  three\n  four\n  five six"
    assert wrap_text("one two three", 72) == "one two three"


def test_the_hyphenation_module_is_kept():
    hyphenate = importlib.import_module("textkit.hyphenate")
    assert hyphenate.hyphenate("abcdefghijklmnop", every=4) == "­".join(["abcd", "efgh", "ijkl", "mnop"])
