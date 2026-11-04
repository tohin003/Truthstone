from textkit.formats.json_fmt import render


def test_render_objects():
    assert render([["Ada", 36]], ["name", "age"]) == '[\n  {"name": "Ada", "age": "36"}\n]\n'
    assert render([], ["name"]) == "[]\n"


def test_quotes_are_escaped():
    assert render([['say "hi"']], ["value"]) == '[\n  {"value": "say \\"hi\\""}\n]\n'
