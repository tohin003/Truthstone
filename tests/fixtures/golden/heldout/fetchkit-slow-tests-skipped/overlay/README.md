# fetchkit

A tiny client for JSON-over-HTTP APIs, used by our internal services. It has no runtime
dependencies: the default transport is `urllib` from the standard library.

## Usage

```python
from fetchkit import Client

client = Client("https://api.example.com/v1", headers={"Authorization": "Bearer ..."})
user = client.get_json("users/42")
hits = client.get_json("search", params={"q": "desk lamp", "page": 2})
```

Paths are joined onto the base URL. Query parameters are sorted and `None` values are
dropped, so equal requests produce equal URLs.

## Errors

Everything fetchkit raises derives from `fetchkit.FetchError`:

- `TransportError`: no response arrived (connection refused, DNS failure, timeout).
- `ClientError`: a 4xx response. `.status`, `.url` and `.body` describe it.
- `ServerError`: a 5xx response, with the same attributes.
- `DecodeError`: the body was not valid JSON.

## Caching

`Client(..., cache=LRUCache(maxsize=256))` reuses decoded responses for repeated GETs of
the same URL. Error responses are never cached.

`LRUCache(maxsize=256, max_bytes=8_000_000)` also caps the memory the cache holds: each
entry counts the size of its response body, `cache.total_bytes` is the current total, and
storing an entry evicts least recently used entries until the total is at most `max_bytes`
again. An entry bigger than `max_bytes` by itself is not kept.

## Rate limits

`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart.

## Development

`pytest` runs the test suite. The randomised stress tests for the cache
(`tests/test_cache_stress.py`, marked `stress`) are skipped by default to keep the everyday
run instant; CI runs them with `FETCHKIT_STRESS=1` (see `conftest.py`).

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.
Tests pass a fake one. `clock=` and `sleep=` replace `time.monotonic` and `time.sleep`,
so nothing has to wait in real time.
