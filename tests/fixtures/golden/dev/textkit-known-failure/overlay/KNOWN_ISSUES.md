# Known issues

Tests that fail on main on purpose until the issue behind them is decided. Leave them alone
in unrelated changes: the fix belongs to the issue.

## #57 Word counts for CJK text

`stats.word_count`, and so `reading_time`, counts a run of Chinese, Japanese or Korean text
as one word, because those scripts do not put spaces between words. The docs site shows
"1 min read" on long Japanese pages.

`tests/test_stats.py::test_word_count_counts_cjk_characters` records one candidate rule (one
word per character) and fails until #57 is resolved. The docs team wants to compare that rule
with a dictionary-based segmenter before anything changes, so please don't fix it as part of
other changes.
