"""comment_block turns free text into a '# ' comment block, as the request specifies."""

from textkit.comments import comment_block


def test_single_short_paragraph():
    assert comment_block("Hello world.") == "# Hello world."


def test_lines_fit_the_width_including_the_prefix():
    assert comment_block("one two three four five", width=12) == "# one two\n# three four\n# five"


def test_paragraphs_are_separated_by_a_bare_hash_line():
    assert comment_block("First paragraph.\n\nSecond one.") == "# First paragraph.\n#\n# Second one."


def test_line_breaks_inside_a_paragraph_are_reflowed():
    assert comment_block("alpha\nbeta gamma", width=40) == "# alpha beta gamma"


def test_default_width_is_72():
    text = " ".join(["word"] * 40)
    lines = comment_block(text).split("\n")
    assert all(line.startswith("# ") and len(line) <= 72 for line in lines)
    assert max(len(line) for line in lines) > 60
    assert " ".join(line[2:] for line in lines) == text


def test_every_line_fits_at_several_widths():
    text = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n\n"
        "Sed do eiusmod tempor incididunt ut labore."
    )
    for width in (20, 30, 50):
        out = comment_block(text, width)
        assert all(len(line) <= width for line in out.split("\n"))
        assert out.count("\n#\n") == 1
        assert not out.endswith("\n")
