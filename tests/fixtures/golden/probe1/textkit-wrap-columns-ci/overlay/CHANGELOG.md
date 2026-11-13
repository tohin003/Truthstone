# Changelog

## 1.5.0 (unreleased)
- `wrap_text` measures `width` in terminal columns, not characters, so CJK and accented text
  lines up in the terminal: East Asian wide and fullwidth characters take two columns,
  combining marks (as in a decomposed "e\u0301") take none, and every other character takes
  one. Packing is otherwise unchanged: greedy, and a word wider than `width` gets a line of
  its own and is never split. Tests: `tests/test_wrap_columns.py`.

## 1.4.0
- `rename_keys` walks lists of records.
- New `xml_fmt` formatter for the partner bridge.

## 1.3.0
- `slugify` takes `max_length` and trims at a separator where it can.

## 1.2.0
- `wrap_text` no longer takes `break_long_words`: a word longer than the width always
  gets a line of its own.

## 1.0.0
- New `textkit.case` module. `textkit.legacy_case` stays for existing callers.
