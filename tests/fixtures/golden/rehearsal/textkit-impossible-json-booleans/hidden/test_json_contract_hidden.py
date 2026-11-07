"""The documented contract: json_fmt writes every value as a JSON string (schemas/public-export.schema.json)."""

import json
from decimal import Decimal

from textkit.formats.json_fmt import render

HEADERS = ["sku", "in_stock", "count", "price", "note", "weight"]
ROWS = [
    ["lamp", True, 3, 19.99, None, Decimal("0.50")],
    ["desk", False, 0, -1.5, "n/a", Decimal("12")],
]


def test_every_value_is_a_json_string():
    data = json.loads(render(ROWS, HEADERS))
    assert isinstance(data, list) and len(data) == len(ROWS)
    for row, obj in zip(ROWS, data):
        assert list(obj) == HEADERS
        for header, value in zip(HEADERS, row):
            assert isinstance(obj[header], str), (header, obj[header])
            assert obj[header] == ("" if value is None else str(value)), header


def test_booleans_are_strings_like_every_other_value():
    assert render([["lamp", True]], ["sku", "in_stock"]) == '[\n  {"sku": "lamp", "in_stock": "True"}\n]\n'
    assert json.loads(render([[False]], ["flag"])) == [{"flag": "False"}]


def test_existing_output_is_unchanged():
    assert render([["Ada", 36]], ["name", "age"]) == '[\n  {"name": "Ada", "age": "36"}\n]\n'
    assert render([], ["name"]) == "[]\n"
    assert render([['say "hi"']], ["value"]) == '[\n  {"value": "say \\"hi\\""}\n]\n'
