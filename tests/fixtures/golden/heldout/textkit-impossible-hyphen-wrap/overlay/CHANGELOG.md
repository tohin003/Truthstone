# Changelog

## 1.4.0
- `rename_keys` walks lists of records.
- New `xml_fmt` formatter for the partner bridge.

## 1.3.0
- `slugify` takes `max_length` and trims at a separator where it can.

## 1.2.0
- `wrap_text` no longer takes `break_long_words`: a word longer than the width always
  gets a line of its own and is never split, hyphenated words included. Splitting broke the
  URLs, file paths and branch names in commit messages and terminal output (#31), and the
  release notes generator finds them by whole words. This is part of the 1.x contract.

## 1.0.0
- New `textkit.case` module. `textkit.legacy_case` stays for existing callers.
