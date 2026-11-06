# Changelog

## 1.4.0
- Optional orjson speed-up for decoding (`fetchkit[speedups]`).
- A `test` extra with the test runner (`pip install -e ".[test]"`).

## 1.3.0
- `min_interval` spaces requests out for rate-limited APIs.

## 1.2.0
- Optional response cache (`LRUCache`). Error responses are not cached.

## 1.1.0
- Query parameters are sorted and `None` values are dropped.
- Absolute URLs passed as paths are refused instead of silently changing hosts.
