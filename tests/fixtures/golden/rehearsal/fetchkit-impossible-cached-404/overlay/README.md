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
the same URL. Error responses, 4xx and 5xx alike, are never cached: a 404 for a user who signs
up a minute later, or a 429 during a burst, must not stick for the life of the cache. The
account and billing services rely on this.

## Rate limits

`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart.

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.
Tests pass a fake one. `clock=` and `sleep=` replace `time.monotonic` and `time.sleep`,
so nothing has to wait in real time.
