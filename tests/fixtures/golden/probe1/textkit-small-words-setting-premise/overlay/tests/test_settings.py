from textkit import settings
from textkit.stats import reading_time
from textkit.wrap import wrap_text


def test_wrap_width_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "WRAP_WIDTH", 9)
    assert wrap_text("the quick brown fox") == "the quick\nbrown fox"


def test_reading_speed_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "WORDS_PER_MINUTE", 2)
    assert reading_time("one two three") == 2
