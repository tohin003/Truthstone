import pytest

from textkit.hyphenate import SOFT_HYPHEN, hyphenate


def test_short_words_are_left_alone():
    assert hyphenate("table") == "table"
    assert hyphenate("twelveletter") == "twelveletter"


def test_long_words_get_soft_hyphens():
    assert hyphenate("internationalisation") == SOFT_HYPHEN.join(["intern", "ationa", "lisati", "on"])


def test_every_must_be_at_least_two():
    with pytest.raises(ValueError):
        hyphenate("word", every=1)
