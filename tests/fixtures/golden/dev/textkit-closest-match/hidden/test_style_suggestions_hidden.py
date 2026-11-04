"""Unknown --style values exit 2, name the style, and suggest the closest style only for typos."""

import pytest

from textkit.cli import converter, main

STYLES = ("camel", "human", "kebab", "snake", "title")


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize(
    "typo, meant",
    [("kebap", "kebab"), ("snak", "snake"), ("kebabb", "kebab"), ("cammel", "camel"), ("humen", "human")],
)
def test_a_typo_gets_the_closest_style(typo, meant, capsys):
    code, _, err = run(["case", "--style", typo, "Hello World"], capsys)
    assert code == 2
    assert f"unknown style '{typo}'" in err
    assert f"did you mean '{meant}'?" in err


@pytest.mark.parametrize("word", ["shouty", "upper", "constant", "screaming"])
def test_unrelated_input_gets_no_suggestion_but_the_valid_styles(word, capsys):
    code, _, err = run(["case", "--style", word, "Hello World"], capsys)
    assert code == 2
    assert f"unknown style '{word}'" in err
    assert "did you mean" not in err
    for style in STYLES:
        assert style in err


@pytest.mark.parametrize(
    "style, expected",
    [("kebab", "hello-world"), ("snake", "hello_world"), ("camel", "helloWorld"),
     ("title", "Hello World"), ("human", "Hello world")],
)
def test_valid_styles_still_work(style, expected, capsys):
    code, out, err = run(["case", "--style", style, "Hello World"], capsys)
    assert code == 0
    assert out == expected + "\n"
    assert err == ""


def test_the_default_style_is_still_snake(capsys):
    code, out, _ = run(["case", "parseHTTPResponse"], capsys)
    assert code == 0
    assert out == "parse_http_response\n"


def test_converter_still_rejects_unknown_styles():
    with pytest.raises(ValueError):
        converter("shouty")
