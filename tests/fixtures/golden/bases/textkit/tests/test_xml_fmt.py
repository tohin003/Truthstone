from textkit.formats.xml_fmt import render


def test_render_rows():
    assert render([["Ada", 36]], ["name", "age"]) == (
        "<rows>\n  <row><name>Ada</name><age>36</age></row>\n</rows>\n"
    )


def test_less_than_is_escaped():
    assert render([["a<b"]], ["value"]) == "<rows>\n  <row><value>a&lt;b</value></row>\n</rows>\n"
