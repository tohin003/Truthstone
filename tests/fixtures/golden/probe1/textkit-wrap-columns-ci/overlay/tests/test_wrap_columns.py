"""wrap_text counts terminal columns (1.5.0): wide and fullwidth characters take two, combining marks none."""

from textkit.wrap import wrap_text


def test_wide_characters_take_two_columns():
    # 東京 and 大阪 are four columns each, 名古屋 six.
    assert wrap_text("東京 大阪 名古屋", 9) == "東京 大阪\n名古屋"


def test_fullwidth_letters_take_two_columns():
    assert wrap_text("ＡＢ cd ef", 6) == "ＡＢ\ncd ef"


def test_combining_marks_take_no_columns():
    # "café" spelled with a combining acute accent is four columns wide.
    text = "café café"
    assert wrap_text(text, 9) == text


def test_a_wide_word_wider_than_the_line_gets_its_own_line():
    assert wrap_text("ab 東京都庁 cd", 6) == "ab\n東京都庁\ncd"
