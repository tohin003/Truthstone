# Changelog

## Unreleased
- `LRUCache` documents that reading with `get` counts as using an entry, while `in` and `len()` do not.
- The README explains `clock=` and `sleep=` for tests that must not wait.

## 1.3.0
- `min_interval` spaces requests out for rate-limited APIs.

## 1.2.0
- Optional response cache (`LRUCache`). Error responses are not cached.

## 1.1.0
- Query parameters are sorted and `None` values are dropped.
- Absolute URLs passed as paths are refused instead of silently changing hosts.
