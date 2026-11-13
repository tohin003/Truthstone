# Changelog

## 1.3.0
- `min_interval` spaces requests out for rate-limited APIs.

## 1.2.0
- Optional response cache (`LRUCache`).
- Error responses are never cached, 4xx included. This is a promise to every caller, not a
  detail: the signup service polls `users/<id>` until the new account shows up, and the
  billing worker retries `invoices/<id>` after a 409, so a remembered 404 or 409 would hand
  them a stale answer until the entry happens to be evicted. A service that wants to
  remember misses keeps its own record of them. Changing this needs a major version.

## 1.1.0
- Query parameters are sorted and `None` values are dropped.
- Absolute URLs passed as paths are refused instead of silently changing hosts.
