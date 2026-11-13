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

## Rate limits

`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart.

## Retries

`Client(..., max_retries=2)` retries responses with status 429 (Too Many Requests) or 503
(Service Unavailable) up to that many times; other statuses are never retried, and when the
retries run out the last response raises as usual. Before each retry the client waits:

- the `Retry-After` header's value, when the response has one. It is either a number of
  seconds (`Retry-After: 30`) or an HTTP date (`Retry-After: Wed, 21 Oct 2026 07:30:00 GMT`).
  An HTTP date is measured from the response's own `Date` header (the server's clock, not
  ours); a date that is already past means retry at once. Header names are
  case-insensitive, as everywhere in HTTP (proxies often send `retry-after`).
- `retry_wait` seconds (default 1) when there is no `Retry-After`, or when an HTTP date
  cannot be measured because the response has no `Date` header.
- never longer than `max_retry_wait` seconds (default 60).

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.
Tests pass a fake one. `clock=` and `sleep=` replace `time.monotonic` and `time.sleep`,
so nothing has to wait in real time.
