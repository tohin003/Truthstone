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
- `CircuitOpenError`: the circuit breaker is open (see below); nothing was sent.

## Caching

`Client(..., cache=LRUCache(maxsize=256))` reuses decoded responses for repeated GETs of
the same URL. Error responses are never cached.

## Circuit breaker

`Client(..., failure_threshold=5, cooldown=30.0)` stops calling a service that keeps failing.
`failure_threshold=None`, the default, turns the breaker off.

- A *failure* is a request that gets no response (`TransportError`) or a 5xx response
  (`ServerError`). Any other outcome, a 2xx, 3xx or 4xx response (even one whose body is not
  valid JSON), counts as a success: it resets the count of consecutive failures.
- After `failure_threshold` consecutive failures the circuit opens: `get_json` then raises
  `CircuitOpenError` (a `FetchError`) at once, without sending anything.
- From `cooldown` seconds after the circuit opened, the next request is sent as a trial. If it
  succeeds, the circuit closes; if it fails, the circuit opens again for another `cooldown`
  seconds, counted from that failure.
- Responses served from the cache never involve the breaker: they are returned even while the
  circuit is open, and they count as neither successes nor failures.

Time comes from the client's `clock=` (see Transports).

## Rate limits

`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart.

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.
Tests pass a fake one. `clock=` and `sleep=` replace `time.monotonic` and `time.sleep`,
so nothing has to wait in real time.

## Development

```
pip install -e '.[test]'
pytest
```
