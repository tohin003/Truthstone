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

## Timeouts

`Client(..., timeout=2.5)` waits at most 2.5 seconds for each response (default 10);
`get_json(..., timeout=30)` overrides it for one call.

## Caching

`Client(..., cache=LRUCache(maxsize=256))` reuses decoded responses for repeated GETs of
the same URL. Error responses are never cached.

## Rate limits

`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart.

## Service registry

`fetchkit.registry.client_for("billing")` returns a Client for one of our internal services,
set up from `src/fetchkit/services.toml`. The registry ships with fetchkit, so every service
that calls billing does so with the same settings. Each `[service]` table has a `base_url`
and, optionally, `timeout` (seconds per response, default 10) and `min_interval` (seconds
between requests). Unknown keys are errors.

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives; `timeout`
is in seconds, as `urllib` takes it. Tests pass a fake one. `clock=` and `sleep=` replace
`time.monotonic` and `time.sleep`, so nothing has to wait in real time.
