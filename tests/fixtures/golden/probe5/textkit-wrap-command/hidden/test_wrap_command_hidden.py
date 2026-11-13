"""`textkit wrap [--width N] TEXT...`: each TEXT wrapped with wrap_text at N columns (default 72), one
paragraph per argument with a blank line between them; a width below 1 is a usage error (status 2)."""

import pytest

from textkit.cli import main
from textkit.wrap import wrap_text

LONG = (
    "Feature flags let the storefront ship code dark and turn it on for a few users at a time, "
    "which keeps a bad release from reaching everybody at once."
)


def test_wrap_at_a_given_width(capsys):
    assert main(["wrap", "--width", "15", "the quick brown fox jumps over the lazy dog"]) == 0
    assert capsys.readouterr().out == "the quick brown\nfox jumps over\nthe lazy dog\n"


def test_default_width_is_72(capsys):
    assert main(["wrap", LONG]) == 0
    out = capsys.readouterr().out
    assert out == wrap_text(LONG, 72) + "\n"
    assert max(len(line) for line in out.splitlines()) <= 72


def test_each_argument_is_its_own_paragraph(capsys):
    main(["wrap", "--width", "10", "one two three", "four five"])
    assert capsys.readouterr().out == "one two\nthree\n\nfour five\n"


def test_whitespace_collapses_and_long_words_keep_their_own_line(capsys):
    main(["wrap", "--width", "10", "a  supercalifragilistic\n\nword"])
    assert capsys.readouterr().out == "a\nsupercalifragilistic\nword\n"


def exit_status(argv):
    """The command's exit status, whether main() returns it or argparse raises SystemExit."""
    try:
        return main(argv)
    except SystemExit as exc:
        return exc.code


@pytest.mark.parametrize("width", ["0", "-3"])
def test_a_width_below_one_is_a_usage_error(width, capsys):
    assert exit_status(["wrap", "--width", width, "text"]) == 2


def test_other_commands_are_unchanged(capsys):
    main(["slug", "Crème Brûlée"])
    main(["case", "--style", "kebab", "Hello World"])
    assert capsys.readouterr().out == "creme-brulee\nhello-world\n"
