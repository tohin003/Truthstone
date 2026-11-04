from textkit.formats.tsv_fmt import render


def test_render_rows():
    assert render([["Ada", 36], ["Grace", None]], ["name", "age"]) == "name\tage\nAda\t36\nGrace\t\n"


def test_tabs_inside_values_become_spaces():
    assert render([["a\tb"]], ["value"]) == "value\na b\n"
