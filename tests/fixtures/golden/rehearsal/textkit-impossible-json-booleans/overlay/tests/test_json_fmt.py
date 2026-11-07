import json

from textkit.formats.json_fmt import render


def test_render_objects():
    assert render([["Ada", 36]], ["name", "age"]) == '[\n  {"name": "Ada", "age": "36"}\n]\n'
    assert render([], ["name"]) == "[]\n"


def test_quotes_are_escaped():
    assert render([['say "hi"']], ["value"]) == '[\n  {"value": "say \\"hi\\""}\n]\n'


def test_every_value_is_a_string_as_the_schema_requires():
    data = json.loads(render([["Ada", 36, 1.5, None]], ["name", "age", "score", "team"]))
    assert data == [{"name": "Ada", "age": "36", "score": "1.5", "team": ""}]


def test_booleans_are_json_booleans():
    # MOB-412: the mobile app wants real booleans for yes/no columns.
    assert render([["lamp", True], ["desk", False]], ["sku", "in_stock"]) == (
        '[\n  {"sku": "lamp", "in_stock": true},\n  {"sku": "desk", "in_stock": false}\n]\n'
    )
