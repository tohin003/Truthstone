from textkit.formats.csv_fmt import render


def test_render_rows():
    assert render([["Ada", 36], ["Grace", None]], ["name", "age"]) == "name,age\nAda,36\nGrace,\n"


def test_values_with_commas_are_quoted():
    assert render([["Lovelace, Ada", "London"]], ["name", "city"]) == 'name,city\n"Lovelace, Ada",London\n'


def test_another_delimiter():
    assert render([["a;b", 1], ["c, d", None]], ["value", "n"], delimiter=";") == 'value;n\n"a;b";1\nc, d;\n'
