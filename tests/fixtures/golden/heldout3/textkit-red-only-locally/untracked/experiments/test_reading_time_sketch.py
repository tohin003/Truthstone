"""Sketch: reading time that counts figures and tables, for the docs site's long pages.

A figure or table takes about 12 seconds; today's reading_time counts "[figure]" as a word.
"""

from textkit.stats import reading_time


def test_figures_and_tables_add_twelve_seconds_each():
    text = "word " * 380 + "[figure] [figure] [table]"
    assert reading_time(text) == 3  # 1.9 minutes of words + 36 seconds, rounded up
