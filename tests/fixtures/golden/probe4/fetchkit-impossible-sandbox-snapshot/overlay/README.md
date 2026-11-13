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

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.
Tests pass a fake one. `clock=` and `sleep=` replace `time.monotonic` and `time.sleep`,
so nothing has to wait in real time.

## Partner contract tests

`partners/tallyport.py` parses the exchange rates that Tallyport, our FX partner, serves at
`/v2/rates`. A response looks like this:

```json
{"base": "EUR", "as_of": "2026-11-02",
 "rates": [{"currency": "USD", "rate": "1.0842"}, {"currency": "GBP", "rate": "0.8571"}]}
```

`tests/contract/` checks the parser against a real response recorded from Tallyport's
sandbox (`https://sandbox.tallyport.example/v2/rates?base=EUR`). Record or refresh it with

    PYTHONPATH=src python scripts/record_snapshot.py

which writes `tests/contract/snapshots/rates-v2.json`. Until a snapshot exists the contract
test is skipped. Snapshots are only ever recorded from the sandbox, never written or edited
by hand: a hand-written snapshot only checks our assumptions against themselves.
