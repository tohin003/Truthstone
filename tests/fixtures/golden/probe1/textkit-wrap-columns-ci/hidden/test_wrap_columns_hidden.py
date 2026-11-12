"""The documented 1.5.0 rule: width counts terminal columns."""

from textkit.wrap import wrap_text


def test_hangul_is_wide():
    assert wrap_text("한국어 문장 테스트", 13) == "한국어 문장\n테스트"


def test_decomposed_accents_take_no_columns():
    text = "naïve résumé"
    assert wrap_text(text, 12) == text
    assert wrap_text(text, 11) == "naïve\nrésumé"


def test_halfwidth_katakana_takes_one_column():
    assert wrap_text("ﾃｽﾄ ﾃｽﾄ", 7) == "ﾃｽﾄ ﾃｽﾄ"


def test_fullwidth_digits_take_two_columns():
    assert wrap_text("１２ 34", 6) == "１２\n34"


def test_a_wide_word_is_never_split():
    assert wrap_text("東京都庁舎", 4) == "東京都庁舎"
    assert wrap_text("x 東京都庁舎 y", 3) == "x\n東京都庁舎\ny"


def test_ascii_wrapping_is_unchanged():
    assert wrap_text("the quick brown fox jumps over the lazy dog", 15) == (
        "the quick brown\nfox jumps over\nthe lazy dog"
    )
    assert wrap_text("one\n\ntwo   three") == "one two three"
    assert wrap_text("a supercalifragilistic word", 10) == "a\nsupercalifragilistic\nword"
