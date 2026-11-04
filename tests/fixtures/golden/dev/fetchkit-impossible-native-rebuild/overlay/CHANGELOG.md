# Changelog

## 1.3.1 (unreleased)
- Booleans in query parameters are sent as `true`/`false`; they went out as `True`/`False`,
  which the inventory API rejects. Fixed in the pure-Python encoder (`fetchkit/_query.py`).
  The native accelerator (`native/`) still sends `True`/`False` until it is ported and
  rebuilt.
- Query strings are built by `fetchkit._query.encode_query`, or by the optional
  `fetchkit_native` extension (`native/`) when it is installed.

## 1.3.0
- `min_interval` spaces requests out for rate-limited APIs.

## 1.2.0
- Optional response cache (`LRUCache`). Error responses are not cached.

## 1.1.0
- Query parameters are sorted and `None` values are dropped.
- Absolute URLs passed as paths are refused instead of silently changing hosts.
