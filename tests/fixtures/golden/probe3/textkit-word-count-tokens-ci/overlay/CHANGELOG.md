# Changelog

## 1.5.0 (unreleased)
- `word_count` counts numbers with separators (`1,250.75`), web addresses and e-mail
  addresses as one word each (see "Word counts" in the README). The docs site's reading
  times depend on it.

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
