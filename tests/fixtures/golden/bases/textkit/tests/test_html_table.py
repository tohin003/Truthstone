from textkit.formats.html_table import render


def test_render_table():
    assert render([["Ada", 36]], ["name", "age"]) == (
        "<table>\n"
        "<thead><tr><th>name</th><th>age</th></tr></thead>\n"
        "<tbody>\n"
        "<tr><td>Ada</td><td>36</td></tr>\n"
        "</tbody>\n"
        "</table>\n"
    )


def test_tags_in_values_are_escaped():
    assert "<td>x &lt; y</td>" in render([["x < y"]], ["value"])
