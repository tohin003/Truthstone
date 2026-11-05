# Changelog

## 1.4.0
- `rename_keys` walks lists of records.
- New `xml_fmt` formatter for the partner bridge.

## 1.3.0
- `slugify` takes `max_length` and trims at a separator where it can.

## 1.2.0
- Removed the `ini_fmt` and `rst_table` formatters (no consumers left).
- `wrap_text` no longer takes `break_long_words`: a word longer than the width always
  gets a line of its own.

## 1.0.0
- New `textkit.case` module. `textkit.legacy_case` stays for existing callers.
